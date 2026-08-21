"""Pump-Fade Strategy — Faz 268-sonrası, kullanıcının kendi sözleriyle:
"Marketteki bütün coinlere ihtiyacımız var... Son iki günde %100 yapmış
coinleri bulacak, shortlayacak, kasanın %5'i kadar 5x pozisyona girecek,
%100 yaptığında çıkacak... AI karar/confidence vs. bunlarla işi yok, mevcut
sistemden yalıtık olması lazım."

Bu modül GERÇEKTEN yalıtık: council/belief/risk-onay zincirinden hiçbirini
çağırmaz — kendi mekanik kuralına uyan bir sembol bulduğunda DecisionEvent'i
doğrudan kurup DecisionPersistor ile decisions tablosuna yazar
(experiment_bucket="pump_fade_v1" ile etiketli). Kapanış için AYRI bir
mekanizma YOK — services/position_closer.py::PositionCloser.
close_due_positions() zaten tüm açık pozisyonları (kaynağından bağımsız)
stop_loss_price/take_profit_price/liquidation_price alanlarına göre kontrol
edip kapatıyor; burada sadece bu alanları doğru kuruyoruz.

İzolasyonun tamamlanması için services/risk_state.py'nin kill switch'i ve
Concept Drift teşhisi de bu deneyin kapanışlarını hariç tutacak şekilde
güncellendi (bkz. o dosyadaki exclude_experiment_bucket kullanımı) — aksi
halde bu mekanik stratejinin kendi (AI'dan çok farklı) kâr/zarar dağılımı
AI'ın kill switch'ini sessizce tetikleyebilirdi.
"""
from datetime import UTC, datetime

import httpx
import structlog

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import OHLCVProvider, get_ohlcv_provider
from simulator.margin import compute_liquidation_price, max_safe_leverage

logger = structlog.get_logger()

EXPERIMENT_BUCKET = "pump_fade_v1"

# Binance Futures — spot exchangeInfo'dan (exchange_gateway/binance/adapter.py
# ::get_symbols) KASITLI OLARAK ayrı: burada gerçekten işlem gören USDT-
# marjinli PERPETUAL sözleşmelerin tam listesi gerekiyor, spot semboller değil.
_FUTURES_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"


def fetch_usdt_perpetual_symbols() -> list[str]:
    """Gerçek Binance Futures exchangeInfo — TÜM işlem gören (status=TRADING)
    USDT-marjinli perpetual (contractType=PERPETUAL) sözleşmeler. Ağ/HTTP
    hatasında fail-closed: boş liste — bu döngüde hiçbir aday bulunmaz, asla
    uydurma/eski bir sembol listesi kullanılmaz."""
    try:
        resp = httpx.get(_FUTURES_EXCHANGE_INFO_URL, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return [
            s["symbol"]
            for s in data.get("symbols", [])
            if s.get("quoteAsset") == "USDT"
            and s.get("contractType") == "PERPETUAL"
            and s.get("status") == "TRADING"
        ]
    except Exception as exc:
        logger.warning("pump_fade_symbol_fetch_failed", error=str(exc))
        return []


def find_pump_candidates(
    symbols: list[str],
    provider: OHLCVProvider,
    lookback_hours: int,
    min_gain_pct: float,
    peak_window_hours: int,
    max_pullback_from_peak_pct: float,
    momentum_confirmation_hours: int,
    momentum_tolerance_pct: float,
) -> list[dict]:
    """Her sembol için gerçek son `lookback_hours` saatlik (1h mumlarla)
    geçmişteki EN DÜŞÜK kapanıştan güncel kapanışa kazanç oranını hesaplar.
    Veri çekilemeyen (ör. futures'ta işlem görüp spot'ta listelenmemiş — bu
    sistemin OHLCV kaynağı spot klines kullanıyor, bkz. market_data/
    ingestion/data_provider.py::BinanceProvider) semboller sessizce atlanır,
    tarama asla bir sembol yüzünden bütünüyle durmaz.

    Faz 292 — kullanıcı bulgusu (gerçek CHIPUSDT örneği): "%15+ kazanç"
    tek başına giriş zamanlamasını hiç garanti etmiyordu — fiyat zirveden
    günlerdir geri çekilip ÇOKTAN dönmeye başlamış olsa bile hâlâ eşiği
    geçiyor olabilir. İki BAĞIMSIZ, kesin tanımlı ek filtre — ikisi de
    (min_gain_pct'e EK olarak) geçmeli, ikisi de zaten fetch edilmiş
    `bars`'ın bir alt-penceresinden hesaplanıyor (ekstra ağ isteği yok):
    zirve yakınlığı (fiyat hâlâ kısa-vadeli zirveye yakın mı) ve kısa
    vadeli momentum teyidi (fiyat son birkaç saatte zaten toparlanmaya
    başlamış mı)."""
    candidates = []
    for symbol in symbols:
        try:
            bars = provider.get_ohlcv(symbol, "1h", limit=lookback_hours)
        except Exception:
            continue
        if len(bars) < 2:
            continue
        low = min(b.low for b in bars)
        current = bars[-1].close
        if low <= 0 or current <= 0:
            continue
        gain_pct = (current - low) / low
        if gain_pct < min_gain_pct:
            continue

        peak_window = bars[-peak_window_hours:] if len(bars) >= peak_window_hours else bars
        recent_peak = max(b.high for b in peak_window)
        if recent_peak <= 0:
            continue
        pullback_from_peak_pct = (recent_peak - current) / recent_peak
        if pullback_from_peak_pct > max_pullback_from_peak_pct:
            continue

        momentum_window = (
            bars[-(momentum_confirmation_hours + 1):]
            if len(bars) > momentum_confirmation_hours
            else bars
        )
        momentum_pct = None
        if len(momentum_window) >= 2:
            reference_close = momentum_window[0].close
            if reference_close > 0:
                momentum_pct = (current - reference_close) / reference_close
                if momentum_pct > momentum_tolerance_pct:
                    continue

        candidates.append({
            "symbol": symbol,
            "gain_pct": gain_pct,
            "current_price": current,
            "pullback_from_peak_pct": pullback_from_peak_pct,
            "momentum_pct": momentum_pct,
        })
    return candidates


_DENSITY_HISTORY_LIMIT = 1000
_DENSITY_MIN_HISTORY = 50
_DENSITY_HIGH_PERCENTILE = 0.90
_DENSITY_FLOOR_MULTIPLIER = 0.5


def _compute_density_size_multiplier(session, candidates_found: int) -> float:
    """Faz 295 — kullanıcı isteği (2026-08-19): pump_fade'in gerçek
    mekanik geri-testinde (4205 olay, 527 sembol) kayıpların zamanda
    RASTGELE dağılmadığı, çok sayıda sembolün AYNI ANDA pompalandığı
    ("altseason" benzeri) haftalarda belirgin şekilde arttığı bulundu
    (kayıp haftalarında ortalama olay yoğunluğu, tüm haftaların
    ortalamasından %32 daha yüksekti — 90.2 vs 68.3). BTC'nin kendi
    yönü belirleyici DEĞİLDİ (en sert BTC düşüşü haftası — %14 —
    neredeyse hiç kayıp vermedi) — asıl risk sinyali "şu an kaç sembol
    aynı anda pump kriterini karşılıyor" yoğunluğuydu, BTC fiyatı değil.

    system_events'e ("pump_fade_candidate_density") her cycle'da
    candidates_found kaydedilip kendi GERÇEK geçmişine göre yüzdelik
    dilimi hesaplanıyor — sabit bir sayı icat edilmiyor, sistem zaman
    içinde kendi normal yoğunluk dağılımını öğreniyor (_volatility_
    regime/_realized_vol_percentile ile AYNI desen). Yeterli geçmiş
    yoksa (<50 kayıt, fail-closed) çarpan 1.0 — mevcut davranış hiç
    değişmez. Yoğunluk kendi geçmişinin üst %10'unda (p90+) ise margin
    lineer olarak [1.0, 0.5] aralığında küçültülüyor — SADECE küçültür,
    asla büyütmez (CPPI/Kelly ile AYNI ilke).

    Faz 306 — kullanıcı isteği: "dominans'ı entegre ettiğimizde buraya da
    bağlayalım." BTC dominansı (market_data/onchain/onchain_provider.py::
    fetch_btc_dominance_pct) her cycle'da AYNI olaya kaydediliyor — ama
    çarpan formülü HENÜZ bunu kullanmıyor, sadece gözlem/birikim. Sezonun
    başında kaçınılan hatayı (2-of-3 Hurst vote'un ampirik doğrulama
    olmadan %41.5 tetikleme oranına çıkması) tekrarlamamak için: dominans
    trendiyle yoğunluk arasındaki gerçek ilişki yeterli geçmiş birikene
    kadar (bu alan hiç yoksa henüz) ölçülmeden çarpana KARIŞTIRILMIYOR."""
    from database.repositories.event_log_repository import EventLogRepository
    from market_data.onchain.onchain_provider import fetch_btc_dominance_pct

    repo = EventLogRepository(session)
    repo.record(
        "pump_fade_candidate_density",
        payload={"candidates_found": candidates_found, "btc_dominance_pct": fetch_btc_dominance_pct()},
    )

    history = repo.list_events(event_type="pump_fade_candidate_density", limit=_DENSITY_HISTORY_LIMIT)
    counts = [
        h["payload"]["candidates_found"] for h in history
        if h.get("payload") and "candidates_found" in h["payload"]
    ]
    if len(counts) < _DENSITY_MIN_HISTORY:
        return 1.0

    # Eşitlikleri (ör. geçmişin büyük kısmı sabit bir değerdeyse) doğru
    # ele almak için: kesin küçükler tam, eşit olanlar yarım ağırlıkla
    # sayılıyor (standart "mid-rank" yüzdelik dilim tanımı) — aksi halde
    # sabit bir geçmişte HER normal değer bile yanlışlıkla p100 çıkardı.
    rank_less = sum(1 for c in counts if c < candidates_found)
    rank_equal = sum(1 for c in counts if c == candidates_found)
    percentile = (rank_less + 0.5 * rank_equal) / len(counts)
    if percentile < _DENSITY_HIGH_PERCENTILE:
        return 1.0

    span = 1.0 - _DENSITY_HIGH_PERCENTILE
    progress = (percentile - _DENSITY_HIGH_PERCENTILE) / span if span > 0 else 1.0
    multiplier = 1.0 - progress * (1.0 - _DENSITY_FLOOR_MULTIPLIER)
    return max(_DENSITY_FLOOR_MULTIPLIER, min(1.0, multiplier))


_REGIME_GATE_MIN_SYMBOLS_PER_SIDE = 5
_REGIME_GATE_WIN_RATE_GAP_MIN = 0.30
_REGIME_GATE_LONG_WIN_RATE_MIN = 0.5
_REGIME_GATE_FLOOR_MULTIPLIER = 0.15
_REGIME_GATE_BTC_DAILY_BARS = 250

# Faz 327 — kullanıcı bulgusu (2026-08-20, canlı, tekrarlayan): BTC
# "transition" rejimindeyken (kesin bull_trend değil) gate hiç
# tetiklenmiyordu, council farkı ne kadar ezici olursa olsun (gerçek
# olay: %79.6 LONG'a karşı %0 SHORT, gap %79.6 — eşiğin (%30) neredeyse
# 3 katı — yine de 5 pump_fade SHORT tek cycle'da tam boyutta açıldı,
# $274K toplam notional). "Önce izleyelim" kararının ardından AYNI
# şikayet tekrar edince müdahale kararı verildi. Kademeli 2. seviye:
# BTC transition'dayken bile council farkı BU eşiği (mevcut %30
# eşiğinin 2 katı — az sayıda gerçek "aşırı ezici" durumu yakalasın,
# sıradan bir LONG yatkınlığını değil) aşıyorsa DAHA HAFİF bir küçültme
# uygulanır — BTC gerçekten bull_trend'deyken kullanılan en sert taban
# (0.15) SADECE o durumda kalır, orantılı bir tepki.
_REGIME_GATE_STRONG_BIAS_GAP_MIN = 0.60
_REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER = 0.5

# Faz 332 — kritik bulgu, gerçek CANLI durumda yakalandı: BTC 5 günde
# ~%20 sıçramıştı (64.532 -> 77.410) ama 200-EMA bazlı long_term_trend_
# regime hâlâ "transition" diyordu (uzun-vade ortalamanın hızlı harekete
# doğal gecikmesi) VE aynı anda açık AI SHORT pozisyon sayısı (2) min.
# örneklem eşiğinin (5) altındaydı — council_bull_bias hesaplanamadı.
# Sonuç: LONG'ların %94.7'si (n=38, GÜÇLÜ bir örneklem) kârdayken bile
# çarpan 1.0 kalıyordu. LONG tarafı TEK BAŞINA yeterince büyük VE
# yeterince ezici bir örneklemse (SHORT tarafının örneklem yetersizliği
# yüzünden "gap" hiç hesaplanamasa bile), bu da bağımsız bir bull
# sinyali sayılır — 0.90 eşiği kasıtlı olarak _REGIME_GATE_LONG_WIN_
# RATE_MIN'den (0.5) çok daha sıkı: SADECE gerçekten ezici bir LONG
# baskınlığında tetiklenir.
_REGIME_GATE_LONG_ONLY_STRONG_SIGNAL_MIN = 0.90


def _compute_regime_size_multiplier(session, provider: OHLCVProvider) -> float:
    """Faz 318 — kullanıcı bulgusu (2026-08-20, canlı): pump_fade HER ZAMAN
    SHORT açar, council/AI zincirinden bilinçli izole (bkz. modül
    docstring'i) — bu YÖN körlüğü demek, piyasanın genel yönüyle ilgili
    SIFIR kanıt kullanmıyor. Canlıda ölçüldü: aynı anda AI'nın kendi
    LONG pozisyonlarının %83'ü kârdaydı (ort. +%3.33) ama SHORT'larının
    %0'ı kârdaydı (ort. -%9.72) — ve pump_fade'in son ~48 saatte açtığı
    79 SHORT'un %85'i zarardaydı (ort. -%3.22). Kullanıcı isteği: "en
    azından elindeki pozisyonları check edemez mi... longlar mı karlı
    gidiyor shortlar mı" + "diğer sinyallerden filtre" — İKİ bağımsız
    kanıt kesişimi (kullanıcı onayı) istendi:

    (1) Council'in KENDİ açık pozisyonlarının GERÇEK şu anki kâr/zarar
        durumu — LONG'ların kârlılık oranı SHORT'lardan anlamlı ölçüde
        (>= 0.30) yüksek VE LONG'lar genel olarak kârdaysa (>= 0.5) —
        ham pozisyon SAYISI değil (bu neredeyse her zaman LONG'a yatkın
        çıkıyor, ayırt edici değil — geriye dönük kontrol edildi: 109
        kapanmış pump_fade işleminin TAMAMI zaten council'in "sayıca
        LONG ağırlıklı" olduğu dönemlerde açılmış, sıfır varyans).
        Kârlılık FARKI ise zamanla gerçekten değişen, canlı bir sinyal.
    (2) BTC'nin gerçek 200-EMA uzun-vade rejimi (long_term_trend_regime)
        bull_trend ise.

    Her iki kanıt da AYNI ANDA doğrulanmazsa çarpan 1.0 — mevcut
    davranış hiç değişmez (fail-closed, az örneklemden veya tek
    sinyalden kalıcı bir karar üretilmez). İkisi de doğrulanırsa margin
    SABİT bir tabana (0.15) küçültülür — SADECE küçültür, pump_fade'i
    hiçbir zaman tamamen KAPATMAZ (kullanıcı kararı: mekanik stratejinin
    kendi kendini tam devre dışı bırakması riskli, insan onayı olmadan).
    Yeterli veri yoksa (az sembol, BTC rejimi hesaplanamıyor) çarpan
    1.0 — _compute_density_size_multiplier ile AYNI fail-closed ilke."""
    from sqlalchemy import text

    from market_data.features.signal_engine import compute_quant_signals

    rows = session.execute(
        text(
            """
            SELECT symbol, direction, AVG(entry_price) AS avg_entry
            FROM decisions
            WHERE status = 'open' AND experiment_bucket IS NULL AND direction IN ('LONG', 'SHORT')
            GROUP BY symbol, direction
            """
        )
    ).fetchall()

    long_win = long_total = short_win = short_total = 0
    for symbol, direction, avg_entry in rows:
        try:
            bars = provider.get_ohlcv(symbol, "1h", limit=2)
            current = bars[-1].close
        except Exception:
            continue
        if not bars or current <= 0 or avg_entry is None or avg_entry <= 0:
            continue
        profitable = (current > avg_entry) if direction == "LONG" else (current < avg_entry)
        if direction == "LONG":
            long_total += 1
            long_win += int(profitable)
        else:
            short_total += 1
            short_win += int(profitable)

    # Faz 332 — kritik bulgu, gerçek veriyle ölçüldü: son 48 saatte rejim
    # gate'inin kapsadığı 43 açılıştan 22'si (%51) hâlâ 1.0x (indirimsiz)
    # çıkmıştı — piyasa BTC bazında açıkça yükseliş trendindeyken bile.
    # Kök neden: BTC rejimi SADECE council_bull_bias (AI'nın kendi AÇIK
    # pozisyonlarının O ANKİ, gürültülü kâr/zarar anlık görüntüsü — az
    # sayıda pozisyon varken tek bir pozisyonun kapanması/dalgalanması
    # eşiği geçip geçmemeyi değiştirebilir) True dönerse hiç kontrol
    # ediliyordu. BTC'nin 200-EMA uzun-vade rejimi çok daha İSTİKRARLI,
    # yapısal bir sinyal — artık council'den TAMAMEN BAĞIMSIZ olarak
    # kendi başına yeterli (PARTIAL_FLOOR), council bias'ı da doğrularsa
    # (iki bağımsız kanıt kesişimi, Faz 318'in orijinal tasarımı) en sıkı
    # tabana (FLOOR) düşülüyor. "Sadece küçültür" ilkesi korunuyor —
    # hiçbir kombinasyon çarpanı 1.0'ın üstüne çıkarmıyor.
    council_bull_bias = False
    win_rate_gap = 0.0
    if long_total >= _REGIME_GATE_MIN_SYMBOLS_PER_SIDE and short_total >= _REGIME_GATE_MIN_SYMBOLS_PER_SIDE:
        long_win_rate = long_win / long_total
        short_win_rate = short_win / short_total
        win_rate_gap = long_win_rate - short_win_rate
        council_bull_bias = (
            long_win_rate >= _REGIME_GATE_LONG_WIN_RATE_MIN
            and win_rate_gap >= _REGIME_GATE_WIN_RATE_GAP_MIN
        )

    # Faz 332 — SHORT tarafında yeterli örneklem YOKSA (ör. şu an açık
    # sadece 1-2 AI SHORT pozisyonu varsa, gap hiç hesaplanamıyorsa),
    # LONG tarafı TEK BAŞINA yeterince büyük VE ezici bir örneklemse
    # (bkz. sabitin üstündeki not) bu da bağımsız bir bull sinyali
    # sayılır. SHORT örneklemi YETERLİYSE (gap zaten hesaplanabiliyorsa)
    # bu dal bilerek devre dışı — o durumda gerçek gap'in kendisi
    # (council_bull_bias) zaten daha güvenilir bir sinyal, LONG'un tek
    # başına iyi görünmesi (SHORT da eşit derecede iyiyken bile) yanlış
    # pozitif üretebilir.
    long_only_strong_bull_signal = (
        short_total < _REGIME_GATE_MIN_SYMBOLS_PER_SIDE
        and long_total >= _REGIME_GATE_MIN_SYMBOLS_PER_SIDE
        and (long_win / long_total) >= _REGIME_GATE_LONG_ONLY_STRONG_SIGNAL_MIN
    )

    try:
        btc_daily = provider.get_ohlcv("BTCUSDT", "1d", limit=_REGIME_GATE_BTC_DAILY_BARS)
        btc_regime = compute_quant_signals(btc_daily).get("long_term_trend_regime")
    except Exception:
        btc_regime = None

    if btc_regime == "bull_trend" and council_bull_bias:
        return _REGIME_GATE_FLOOR_MULTIPLIER
    if btc_regime == "bull_trend":
        return _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER
    if council_bull_bias and win_rate_gap >= _REGIME_GATE_STRONG_BIAS_GAP_MIN:
        return _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER
    if long_only_strong_bull_signal:
        return _REGIME_GATE_PARTIAL_FLOOR_MULTIPLIER
    return 1.0


class PumpFadeStrategy:
    def __init__(self, data_provider: OHLCVProvider | None = None):
        self.data_provider = data_provider or get_ohlcv_provider()

    def run_cycle(self) -> dict:
        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            enabled = settings_repo.get("pump_fade_enabled") == "true"
            if not enabled:
                return {"skipped": "pump_fade_disabled"}

            max_loss_circuit_breaker_usd = float(settings_repo.get("pump_fade_max_loss_circuit_breaker_usd"))
            realized_pnl = DecisionPersistor(session).total_pnl_for_experiment(EXPERIMENT_BUCKET)
            if realized_pnl <= -max_loss_circuit_breaker_usd:
                settings_repo.set("pump_fade_enabled", "false", updated_by="pump_fade_circuit_breaker")
                from database.repositories.event_log_repository import EventLogRepository
                EventLogRepository(session).record(
                    event_type="pump_fade_circuit_breaker_tripped",
                    entity_type="strategy",
                    payload={
                        "realized_pnl": realized_pnl,
                        "threshold_usd": max_loss_circuit_breaker_usd,
                        "reason": "pump_fade toplam gerçekleşmiş zararı eşiği aştı, pump_fade_enabled otomatik false yapıldı",
                    },
                )
                return {"skipped": "circuit_breaker_tripped", "realized_pnl": realized_pnl}

            max_loss_per_trade_usd = float(settings_repo.get("pump_fade_max_loss_per_trade_usd"))
            max_open_positions = int(settings_repo.get("pump_fade_max_open_positions"))
            max_total_capital_pct = float(settings_repo.get("pump_fade_max_total_capital_pct"))
            target_leverage = float(settings_repo.get("pump_fade_leverage"))
            min_gain_pct = float(settings_repo.get("pump_fade_min_gain_pct"))
            lookback_hours = int(settings_repo.get("pump_fade_lookback_hours"))
            stop_distance_pct = float(settings_repo.get("pump_fade_stop_distance_pct"))
            take_profit_pct = float(settings_repo.get("pump_fade_take_profit_pct"))
            starting_capital = float(settings_repo.get("starting_capital"))
            # Faz 292 — giriş-zamanlaması filtreleri (bkz. find_pump_candidates).
            peak_window_hours = int(settings_repo.get("pump_fade_peak_window_hours"))
            max_pullback_from_peak_pct = float(settings_repo.get("pump_fade_max_pullback_from_peak_pct"))
            momentum_confirmation_hours = int(settings_repo.get("pump_fade_momentum_confirmation_hours"))
            momentum_tolerance_pct = float(settings_repo.get("pump_fade_momentum_tolerance_pct"))
            reentry_min_gain_pct = float(settings_repo.get("pump_fade_reentry_min_gain_pct"))

        symbols = fetch_usdt_perpetual_symbols()
        if not symbols:
            return {"skipped": "no_symbols"}

        candidates = find_pump_candidates(
            symbols, self.data_provider, lookback_hours, min_gain_pct,
            peak_window_hours, max_pullback_from_peak_pct,
            momentum_confirmation_hours, momentum_tolerance_pct,
        )

        # Faz 341 — kullanıcı bulgusu: bir sembolde stop olduktan SONRA
        # pump devam ettiği için normal min_gain_pct (%15) hâlâ geçiliyor,
        # sistem hemen aynı sembolde tekrar SHORT açıp tekrar stop
        # oluyordu. Son kapanan pump_fade işlemi stop_loss ile bitmiş bir
        # sembol için, bu döngüde gain_pct daha sıkı reentry_min_gain_pct
        # (%50) eşiğini de geçmeli — geçmezse aday tamamen elenir.
        if candidates:
            with SessionFactory.get_session() as session:
                recently_stopped_symbols = DecisionPersistor(session).symbols_with_last_exit_reason_stop_loss(
                    [c["symbol"] for c in candidates], EXPERIMENT_BUCKET,
                )
            if recently_stopped_symbols:
                candidates = [
                    c for c in candidates
                    if c["symbol"] not in recently_stopped_symbols or c["gain_pct"] >= reentry_min_gain_pct
                ]

        with SessionFactory.get_session() as session:
            density_size_multiplier = _compute_density_size_multiplier(session, len(candidates))
            regime_size_multiplier = _compute_regime_size_multiplier(session, self.data_provider)

        opened = []
        for candidate in candidates:
            result = self._try_open(
                candidate, max_loss_per_trade_usd, target_leverage, stop_distance_pct, take_profit_pct,
                starting_capital, lookback_hours, density_size_multiplier, regime_size_multiplier,
                max_total_capital_pct, max_open_positions,
            )
            if result is not None:
                opened.append(result)

        return {
            "candidates_found": len(candidates),
            "density_size_multiplier": density_size_multiplier,
            "regime_size_multiplier": regime_size_multiplier,
            "opened": opened,
        }

    def _try_open(
        self,
        candidate: dict,
        max_loss_per_trade_usd: float,
        target_leverage: float,
        stop_distance_pct: float,
        take_profit_pct: float,
        starting_capital: float,
        lookback_hours: int,
        density_size_multiplier: float = 1.0,
        regime_size_multiplier: float = 1.0,
        max_total_capital_pct: float = 1.0,
        max_open_positions: int = 20,
    ) -> dict | None:
        symbol = candidate["symbol"]
        entry_price = candidate["current_price"]

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            if persistor.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET):
                return None

            # Faz 332 — kritik bulgu: gerçek olayda 82-99 pozisyon aynı
            # anda, çoğunlukla AYNI yönde (SHORT) ve yüksek korelasyonlu
            # açık kalmıştı — kümülatif MARJİN tavanı (aşağıda) tek
            # başına bunu engellemiyordu (risk-bazlı boyutlandırma
            # sonrası tek pozisyon marjini çok küçüldüğü için tavan çok
            # daha fazla pozisyona "izin verir" hale geldi). Ayrı bir
            # SAYI tavanı çeşitlendirme başarısızlığını doğrudan sınırlıyor.
            if persistor.count_open_positions_for_experiment(EXPERIMENT_BUCKET) >= max_open_positions:
                return None

            # Faz 268-sonrası — kullanıcının onayladığı güvenlik kilidi:
            # hedef kaldıraç (ör. 5x) sadece bir TAVAN. Gerçek uygulanan
            # kaldıraç, likidasyon mesafesinin bu stratejinin kendi güvenlik
            # stop'undan en az 1.5 kat uzakta kalmasını sağlayacak şekilde
            # kırpılır — AI'ın DecisionRecorder'daki AYNI disiplini
            # (simulator/margin.py::max_safe_leverage).
            safe_leverage = max_safe_leverage(stop_distance_pct)
            leverage = target_leverage
            if safe_leverage is not None:
                leverage = max(1.0, min(target_leverage, safe_leverage))

            # Faz 332 — KÖK NEDEN düzeltmesi (bkz. app_settings_repository.py::
            # DEFAULTS["pump_fade_max_loss_per_trade_usd"] üstündeki not):
            # gerçek olay — 82 açık pozisyon, -$453.648 gerçekleşmemiş
            # zarar, eski formül (kasanın sabit %5'i, stop mesafesinden
            # BAĞIMSIZ) tek pozisyonda ~$16.500 kayıp riski taşıyordu.
            # Artık margin, "stop'a takılırsa TAM OLARAK max_loss_per_
            # trade_usd kadar kaybedilsin" eşitliğinden GERİYE hesaplanıyor
            # — stop mesafesi/kaldıraç ne kadar büyükse margin o kadar
            # KÜÇÜLÜYOR (AI council'in Kelly-bazlı sabit-$-risk felsefesiyle
            # AYNI ilke). Faz 295/318 çarpanları (yoğunluk/rejim) hâlâ
            # ÜSTÜNE binip SADECE küçültüyor, hiçbir şey büyütmüyor.
            risk_denominator = stop_distance_pct * leverage
            if risk_denominator <= 0:
                return None
            margin = (max_loss_per_trade_usd / risk_denominator) * density_size_multiplier * regime_size_multiplier

            already_committed = persistor.total_open_margin_for_experiment(EXPERIMENT_BUCKET)
            if already_committed + margin > starting_capital * max_total_capital_pct:
                return None

            # Kullanıcı bulgusu — gerçek olay: PORTALUSDT'de $25.000 marjin
            # × 4,35x kaldıraç = $108.695 notional açıldı, ama RiskEngine'in
            # gerçek max_position_size tavanı $100.000'di. Bu strateji
            # council/RiskEngine zincirinden BİLİNÇLİ olarak izole (AI onayı
            # gerektirmesin diye) — ama bu izolasyon yanlışlıkla güvenlik
            # tavanını da atlıyordu. "Sinyal limitleri gevşetemez, sadece
            # küçültebilir" ilkesi burada da geçerli: notional tavanı
            # aşıyorsa kaldıraç (yukarıdaki likidasyon güvenlik kilidiyle
            # AYNI şekilde) kırpılır; margin'in KENDİSİ bile tavanı
            # aşıyorsa (1x kaldıraçta bile sığmıyor) pozisyon hiç açılmaz.
            from database.repositories.risk_limit_repository import RiskLimitRepository
            max_position_size = RiskLimitRepository(session).get_active("global", "max_position_size")
            if max_position_size is not None:
                if margin > max_position_size.value:
                    return None
                max_leverage_for_cap = max_position_size.value / margin
                leverage = max(1.0, min(leverage, max_leverage_for_cap))

            quantity = (margin * leverage) / entry_price
            final_size = margin / entry_price

            stop_loss_price = entry_price * (1 + stop_distance_pct)
            # Kullanıcı bulgusu — gerçek olay: eski kural "%100 marjin kârında
            # çık" idi (take_profit = entry*(1-1/leverage)) — stop mesafesi
            # genişleyip güvenlik kilidi leverage'ı düşürdükçe bu ham hedef
            # SESSİZCE çok uzağa kayardı (198 gerçek pump olayında ölçüldü:
            # %30 stopta 1/leverage ≈ %45.5, simülasyonun bulduğu en iyi
            # ham hedeften — %25 — çok uzak, EV'i düşürüyordu). Artık hedef
            # doğrudan pump_fade_take_profit_pct'ten (ham %, leverage'dan
            # BAĞIMSIZ) kuruluyor — leverage ne olursa olsun sabit kalır.
            # margin_profit_pct (kaç KATINA denk geldiği) sadece bilgi
            # amaçlı, hiçbir hesaba girmiyor.
            take_profit_price = entry_price * (1 - take_profit_pct)
            margin_profit_pct = take_profit_pct * leverage
            liquidation_price = compute_liquidation_price(entry_price, "SHORT", leverage)

            # Faz 337 — kullanıcı onayı: ExecutionAgent v1 kapsamı SADECE
            # ölçüm/kayıt — margin/quantity/leverage'a HİÇ dokunmuyor,
            # sadece SHORT (yani ask tarafında değil bid tarafında satım)
            # için tahmini yürütme maliyetini agent_opinions'a kaydediyor.
            # Bugünkü krizle DOĞRUDAN ilgili: pump_fade adayları tanım
            # gereği (kısa sürede aşırı hareket etmiş, genelde düşük
            # likiditeli) altcoin'ler — gerçek maliyetin ne kadar büyük
            # olduğunu birkaç hafta ÖLÇMEDEN otomatik bir boyut-küçültme
            # gate'i eklenmiyor (bkz. execution_impact_estimator.py'nin
            # kapsam notu).
            execution_cost_estimate = None
            try:
                from database.repositories.market_data_repository import MarketDataRepository
                from contracts.market_data import DataSource
                from services.execution_impact_estimator import estimate_execution_cost_pct

                order_book = MarketDataRepository(session).get_latest_order_book_snapshot(
                    DataSource.BINANCE, symbol
                )
                execution_cost_estimate = estimate_execution_cost_pct(order_book, margin * leverage, "SHORT")
            except Exception:
                execution_cost_estimate = None

            now = datetime.now(UTC)
            opinions = [{
                "type": "pump_fade_rule",
                "data": {
                    "gain_pct_lookback": candidate["gain_pct"],
                    "lookback_hours": lookback_hours,
                    "pullback_from_peak_pct": candidate["pullback_from_peak_pct"],
                    "momentum_pct": candidate["momentum_pct"],
                    "density_size_multiplier": density_size_multiplier,
                    "regime_size_multiplier": regime_size_multiplier,
                    "stop_distance_pct": stop_distance_pct,
                    "target_leverage": target_leverage,
                    "applied_leverage": leverage,
                    "take_profit_pct": take_profit_pct,
                    "margin_profit_pct": margin_profit_pct,
                },
            }]
            if execution_cost_estimate is not None:
                opinions.append({"type": "execution_cost_estimate", "data": execution_cost_estimate})

            event = DecisionEvent(
                timestamp=now,
                symbol=symbol,
                proposed_direction="SHORT",
                final_action="SHORT",
                final_size=final_size,
                confidence=0.0,
                agent_opinions=opinions,
                status="open",
                entry_price=entry_price,
                quantity=quantity,
                opened_at=now,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                leverage=leverage,
                liquidation_price=liquidation_price,
                timeframe="1h",
                experiment_bucket=EXPERIMENT_BUCKET,
            )
            persistor.persist(event)

        return {
            "symbol": symbol,
            "entry_price": entry_price,
            "gain_pct": candidate["gain_pct"],
            "leverage": leverage,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
        }
