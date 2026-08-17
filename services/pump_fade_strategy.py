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
) -> list[dict]:
    """Her sembol için gerçek son `lookback_hours` saatlik (1h mumlarla)
    geçmişteki EN DÜŞÜK kapanıştan güncel kapanışa kazanç oranını hesaplar.
    Veri çekilemeyen (ör. futures'ta işlem görüp spot'ta listelenmemiş — bu
    sistemin OHLCV kaynağı spot klines kullanıyor, bkz. market_data/
    ingestion/data_provider.py::BinanceProvider) semboller sessizce atlanır,
    tarama asla bir sembol yüzünden bütünüyle durmaz."""
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
        if gain_pct >= min_gain_pct:
            candidates.append({"symbol": symbol, "gain_pct": gain_pct, "current_price": current})
    return candidates


class PumpFadeStrategy:
    def __init__(self, data_provider: OHLCVProvider | None = None):
        self.data_provider = data_provider or get_ohlcv_provider()

    def run_cycle(self) -> dict:
        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            enabled = settings_repo.get("pump_fade_enabled") == "true"
            if not enabled:
                return {"skipped": "pump_fade_disabled"}

            capital_pct = float(settings_repo.get("pump_fade_capital_pct"))
            target_leverage = float(settings_repo.get("pump_fade_leverage"))
            min_gain_pct = float(settings_repo.get("pump_fade_min_gain_pct"))
            lookback_hours = int(settings_repo.get("pump_fade_lookback_hours"))
            stop_distance_pct = float(settings_repo.get("pump_fade_stop_distance_pct"))
            take_profit_pct = float(settings_repo.get("pump_fade_take_profit_pct"))
            starting_capital = float(settings_repo.get("starting_capital"))

        symbols = fetch_usdt_perpetual_symbols()
        if not symbols:
            return {"skipped": "no_symbols"}

        candidates = find_pump_candidates(symbols, self.data_provider, lookback_hours, min_gain_pct)

        opened = []
        for candidate in candidates:
            result = self._try_open(
                candidate, capital_pct, target_leverage, stop_distance_pct, take_profit_pct,
                starting_capital, lookback_hours
            )
            if result is not None:
                opened.append(result)

        return {"candidates_found": len(candidates), "opened": opened}

    def _try_open(
        self,
        candidate: dict,
        capital_pct: float,
        target_leverage: float,
        stop_distance_pct: float,
        take_profit_pct: float,
        starting_capital: float,
        lookback_hours: int,
    ) -> dict | None:
        symbol = candidate["symbol"]
        entry_price = candidate["current_price"]

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            if persistor.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET):
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

            margin = starting_capital * capital_pct

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

            now = datetime.now(UTC)
            event = DecisionEvent(
                timestamp=now,
                symbol=symbol,
                proposed_direction="SHORT",
                final_action="SHORT",
                final_size=final_size,
                confidence=0.0,
                agent_opinions=[{
                    "type": "pump_fade_rule",
                    "data": {
                        "gain_pct_lookback": candidate["gain_pct"],
                        "lookback_hours": lookback_hours,
                        "stop_distance_pct": stop_distance_pct,
                        "target_leverage": target_leverage,
                        "applied_leverage": leverage,
                        "take_profit_pct": take_profit_pct,
                        "margin_profit_pct": margin_profit_pct,
                    },
                }],
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
