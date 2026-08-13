"""Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
getirelim." Bu oturumda scratchpad'de doğrulanan gerçek metodolojinin
(shadow_backtest.py) repo'ya taşınmış, kalıcı hali.

Mevcut backtest/cognitive_backtest_runner.py'den (dashboard'un "Run
Backtest" butonunun kullandığı, MockOHLCVAdapter ile sahte fiyat üreten
yol) KASITLI OLARAK farklı ve AYRI tutuluyor:
- O runner `ctx.market.features`'ı hiç doldurmuyor (dokümante edilmiş bir
  sınırlama) — ATR=0 olduğu için RiskTargetStage/DecisionFusion HER zaman
  reddediyor, 9 ajan council'i kör çalışıyor. Üstüne yön için gerçek
  council yerine sabit bir "close[-1]>=close[0]" sezgisi kullanıyor.
- Burası gerçek Binance geçmiş verisiyle, market_data/features/
  signal_engine.py'nin GERÇEK (üretimde de kullanılan) fonksiyonlarıyla,
  walk-forward (lookahead yok) çalışıyor. Gerçek CognitiveEngine council'i
  gerçek yönü belirliyor. Çıkış, services/position_closer.py::
  _exit_reason ile BİREBİR AYNI mantıkla simüle ediliyor — sabit bir
  ufuk fiyatı değil, gerçek stop/target hangisi önce gerçekleşirse.
  Faz 223a'nın maker/taker ücret ayrımı (take_profit=maker, stop_loss=
  taker) da uygulanıyor.

Risk state'i (üretimdeki gibi DB'den GERÇEK/CANLI okumak yerine) burada
kasıtlı olarak backtest'e özel, izole/gevşek değerlerle kuruluyor —
gerçek üretimin "şu an kaç pozisyon açık" gibi CANLI durumunu bir geçmiş
simülasyonuna sızdırmamak için (services/orchestrator.py::
build_cognitive_context()'i DOĞRUDAN çağırmıyoruz, ama AYNI signal_engine
fonksiyonlarını kullanıyoruz — "iki beyin" riski sinyal hesaplamasında
yok, sadece risk-context kurulumunda kasıtlı bir ayrım var)."""
from datetime import timedelta

from analytics.mae_mfe import compute_mae_mfe
from contracts.agent import VOTING_AGENT_DOMAINS
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskLimitEntry
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from exchange_gateway.binance.adapter import BinanceAdapter
# Faz 236: kritik bulgu — asyncio.run() zaten çalışan bir event loop
# içinden (ör. bu backtest'i tetikleyen async FastAPI endpoint'i, ya da
# celery task_always_eager modu) çağrılırsa RuntimeError fırlatır — aynı,
# önceden market_data/ingestion/data_provider.py'de bulunup düzeltilen bug.
# Aynı paylaşılan çözüm burada da kullanılıyor.
from market_data.ingestion.data_provider import _run_coroutine_sync
from market_data.features.signal_engine import (
    compute_daily_atr_pct,
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from market_data.ingestion.ohlcv import OHLCV, from_binance_klines
from services.cognitive_engine import CognitiveEngine
from simulator.fee_engine import FeeEngine
from simulator.slippage_model import SlippageModel

# Faz 248: kullanıcı isteği — "elimizde gerçek geçmiş veriyle binlerce
# deneme yapabilecek bir motor var ama öğrenme döngüsüne bağlı değil,
# neden bağlamıyoruz." Gerçek kısıt: yaşıyor işlem hacmi (canlıda haftalar
# süren ~500 kapanmış işlem) AgentMemory/WeightOptimizer'ın istatistiksel
# örneklem büyüklüğünü çok yavaş büyütüyor. Bu motor zaten gerçek Binance
# geçmiş verisiyle, gerçek CognitiveEngine council'iyle, gerçek exit
# mantığıyla çalışıyor — sadece sonuçlar hiçbir yere kaydedilmiyordu.
_VALID_AGENT_DOMAINS = VOTING_AGENT_DOMAINS


# Faz 268-sonrası — kritik bulgu (2026-08-13): lookback her walk-forward
# adımında SABİT bir pencere (bkz. aşağıdaki `bars[max(0, t-lookback):t+1]`)
# — asla büyümüyor, `t` ne kadar ilerlerse ilerlesin özellik motoruna HER
# ZAMAN en fazla `lookback` bar veriliyor. market_data/features/
# signal_engine.py::_long_term_trend_regime en az 220 bar istiyor (gerçek
# 200-EMA + yakınsama tamponu); eski varsayılan (100) bu özelliği HİÇBİR
# backtest çalıştırmasında asla çözülmeyecek şekilde kilitliyordu —
# 1512 işlemlik gerçek bir OOS koşusunda regime %100 "insufficient_data"
# çıktı, QuantAgent'ın uzun-vade rejim kanıtı sürekli eksikti. Var olan
# testlerin TAMAMI lookback'i açıkça kendi geçiyor (bu varsayılanı hiç
# kullanmıyor) — değişiklik onları etkilemiyor.
DEFAULT_LOOKBACK = 230
DEFAULT_MAX_FORWARD_BARS = 200

# Faz 268d — kritik bulgu: son 3 backtest çalıştırması (15m, iki tekli
# BTCUSDT/ETHUSDT ve bir SOLUSDT+BNBUSDT) 0 işlem üretti. Gerçek veriyle
# doğrulandı: bu dosya risk (stop/target) tabanını backtest'in KENDİ
# `timeframe`'inden bağımsız, HER ZAMAN gerçek GÜNLÜK ATR'den kuruyordu
# (aşağıdaki eski `daily_bars = fetch_real_history(symbol, "1d", 400)`).
# BTCUSDT örneği: günlük ATR ~%2.0, 1:4 oranla hedef mesafesi ~$5188 —
# ama test edilen 300 bar'lık (75 saatlik) 15m penceresinde fiyat baştan
# sona sadece $1520 aralığında kaldı. Hedefe ulaşmak MATEMATİKSEL OLARAK
# imkansızdı, max_forward_bars (200 bar = 50 saat) içinde hiçbir pozisyon
# kapanamadı (120/120 "open_positions_never_closed"). Bu, canlıda Faz
# 262b/265'in düzelttiği AYNI hata sınıfı ("kısa-vadeli katmana günlük
# ATR tabanlı, çok geniş hedef") — ama o düzeltme sadece services/
# orchestrator.py::propose()'a uygulanmıştı, bu backtest modülüne hiç
# yansımamıştı. Aynı mantığı burada da uyguluyoruz: risk tabanı artık
# backtest'in KENDİ timeframe'ine göre seçiliyor (candle_timeframe ↔
# risk_timeframe eşlemesi, TRADE_HORIZON_TO_RISK_TIMEFRAME'in ruhu aynı
# ama burada kullanıcı ayarı değil, backtest'in test ettiği timeframe
# giriş noktası).
_BACKTEST_TIMEFRAME_TO_RISK_TIMEFRAME: dict[str, str] = {
    "1m": "1h", "3m": "1h", "5m": "1h",
    "15m": "1h", "30m": "4h",
    "1h": "4h", "2h": "4h", "4h": "4h",
    "1d": "1d",
}

_TIMEFRAME_TO_TIMEDELTA: dict[str, timedelta] = {
    "1m": timedelta(minutes=1), "3m": timedelta(minutes=3), "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15), "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1), "2h": timedelta(hours=2), "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


async def fetch_real_history(symbol: str, timeframe: str, limit: int) -> list[OHLCV]:
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        raw = await adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
    finally:
        await adapter.disconnect()
    return from_binance_klines(raw)


def _risk_atr_pct_asof(
    risk_bars: list[OHLCV], as_of, bar_duration: timedelta, period: int = 14,
) -> float | None:
    """Faz 251/268d: no-lookahead risk ATR — SADECE as_of anından önce
    TAMAMEN kapanmış bar'lar kullanılıyor (bar_duration, o bar'ın ne zaman
    gerçekten kapandığını hesaba katıyor — 1d bar'lar için gün başlangıcı,
    1h/4h bar'lar için kendi süreleri; hâlâ oluşmakta olan/gelecekteki
    hiçbir bar asla dahil edilmiyor)."""
    if not risk_bars:
        return None
    visible = [b for b in risk_bars if b.timestamp + bar_duration <= as_of]
    if len(visible) < period + 1:
        return None
    return compute_daily_atr_pct(visible, period=period)


def _build_backtest_context(
    symbol: str, timeframe: str, window: list[OHLCV], capital_per_trade: float,
    daily_atr_pct: float | None = None,
) -> CognitiveCycleContext:
    """services/orchestrator.py::build_cognitive_context()'in sinyal-
    hesaplama kısmıyla (gerçek technical/quant/pattern) AYNI, ama risk
    state'i backtest'e özel — üretimin canlı DB durumunu (şu an kaç
    pozisyon açık, gerçek starting_capital vb.) bir geçmiş simülasyonuna
    karıştırmıyoruz."""
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = timeframe

    technical = compute_technical_signals(window)
    quant = compute_quant_signals(window)
    pattern = compute_pattern_signals(window)
    ctx.market.features = {**technical, **quant}
    if daily_atr_pct is not None:
        ctx.market.features["daily_atr_pct"] = daily_atr_pct
    ctx.market.raw_snapshot = {
        "close": window[-1].close,
        "volume": window[-1].volume,
        "high": window[-1].high,
        "low": window[-1].low,
        **pattern,
    }

    ctx.risk.limits = {
        "max_position_size": RiskLimitEntry(value=capital_per_trade * 10, hash=""),
        "max_drawdown": RiskLimitEntry(value=0.5, hash=""),
    }
    ctx.risk.trading_mode = "test"
    ctx.risk.ai_enabled = True
    ctx.risk.max_concurrent_positions = 1000
    ctx.risk.open_position_count = 0
    ctx.risk.capital_used_pct = 0.0
    ctx.risk.max_capital_pct = 1.0
    ctx.decision.proposed_size = capital_per_trade / window[-1].close if window[-1].close else 0.0

    return ctx


def _simulate_real_exit(
    bars: list[OHLCV],
    entry_idx: int,
    direction: str,
    stop_price: float | None,
    target_price: float | None,
    max_forward_bars: int,
) -> tuple[float | None, str | None, int | None]:
    """services/position_closer.py::_exit_reason ile BİREBİR AYNI mantık —
    backtest'te "zaman geçmesi" yerine sonraki gerçek bar'lara bakılıyor.
    max_forward_bars içinde stop/target'a hiç ulaşmazsa (None, None, None)
    döner — Faz 216 (vade dolunca kapatma yasak) ile tutarlı olarak,
    sonsuza dek açık kalmış sayılır, uydurma bir kapanış fiyatı İCAT
    EDİLMEZ, işlem sonuçlara dahil edilmez."""
    for fb in range(1, max_forward_bars + 1):
        idx = entry_idx + fb
        if idx >= len(bars):
            break
        bar = bars[idx]
        if direction == "LONG":
            if stop_price is not None and bar.low <= stop_price:
                return stop_price, "stop_loss", idx
            if target_price is not None and bar.high >= target_price:
                return target_price, "take_profit", idx
        else:
            if stop_price is not None and bar.high >= stop_price:
                return stop_price, "stop_loss", idx
            if target_price is not None and bar.low <= target_price:
                return target_price, "take_profit", idx
    return None, None, None


def _record_backtest_agent_learning(agent_memory, opinions, symbol: str, direction: str, net_pnl_usd: float) -> None:
    """PositionCloser._record_agent_learning() ile AYNI mantık (Faz 211/245:
    ajanın KENDİ önerdiği yön gerçekten alınan yönle karşılaştırılır; sadece
    gerçekten yönlü (LONG/SHORT) oy veren ajanlar ölçülür, WAIT ne
    ödüllendirilir ne cezalandırılır) — ama source="backtest" ile açıkça
    etiketlenir, canlı işlemlerle asla sessizce karıştırılmaz."""
    from contracts.agent_performance import AgentPerformanceRecord

    profitable = net_pnl_usd > 0
    for op in opinions or []:
        domain = op.domain.value if hasattr(op.domain, "value") else str(op.domain)
        if domain not in _VALID_AGENT_DOMAINS:
            continue
        agent_direction = (op.direction or "").upper()
        if agent_direction not in ("LONG", "SHORT"):
            continue
        was_correct = profitable if agent_direction == direction else not profitable
        agent_memory.record(AgentPerformanceRecord(
            agent_domain=domain,
            direction=op.direction,
            confidence=op.confidence or 0.0,
            was_correct=was_correct,
            pnl=net_pnl_usd,
            symbol=symbol,
            source="backtest",
        ))


def run_real_backtest(
    symbol: str,
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = DEFAULT_LOOKBACK,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    capital_per_trade: float = 1000.0,
    engine: CognitiveEngine | None = None,
    agent_memory=None,
    reverse_direction: bool = False,
) -> dict:
    """Tek sembol için gerçek Binance geçmiş verisiyle walk-forward
    backtest. Dönen dict, api/rest/backtest.py'nin BacktestRun.metrics'e
    yazdığı gerçek bulgular — icat edilmiş bir sayı yok, açık pozisyonda
    (stop/target'a hiç ulaşmayan) işlemler sonuçlara dahil edilmiyor.

    Faz 268ab — kullanıcının getirdiği "tam tersini yap" teşhis testi:
    reverse_direction=True iken council'in GERÇEK yönlü kararı (LONG/SHORT
    seçimi, WAIT/red mantığı DEĞİL) ters çevrilir, stop/target/slippage/
    ücret hesabı ters çevrilmiş yöne göre AYNI gerçek mantıkla yeniden
    kurulur. Amaç: "sistem trend-following ama kısa vadeli kripto mean-
    reverting mi davranıyor" hipotezini gerçek veriyle ucuzca test etmek
    — canlı MetaStage/DecisionFusion koduna HİÇ dokunulmadan (orada
    değiştirmek riskli olurdu), sadece bu izole backtest fonksiyonunda.

    Faz 248: agent_memory verilirse, her gerçekten kapanan simüle işlemin
    sonucu (gerçek council'in gerçek yönlü oyları + gerçek kâr/zarar)
    source="backtest" etiketiyle AgentMemory'ye kaydedilir — canlı işlem
    hacminin çok yavaş büyüdüğü örneklem boyutunu, gerçek geçmiş veriyle
    hızla büyütmek için. UYARI: aynı geçmiş pencereyi tekrar tekrar
    backtest etmek aynı işlemleri TEKRAR kaydeder (dedup yok) — bilinçli
    bir sınır, çağıran taraf ne sıklıkla besleyeceğine karar vermeli.

    Faz 268-sonrası — kullanıcı bulgusu: bir backtest 392 işlemde %0
    kazanma oranı gösterdi ("bu ne kadar olası ki"). Kök sebep: council
    bu pencerede %90 LONG çağırmış ama fiyat gerçekten düşüyordu (canlıdaki
    AYNI gecikmeli-trend-rejimi olayının bir başka örneği) — ama ayrıca
    şu da doğrulandı: bu backtest'in sonuçları canlı sistemin GERÇEKTEN
    sahip olduğu kill switch/drawdown sizing korumaları OLMADAN
    üretiliyordu (_build_backtest_context hiçbir zaman consecutive_losses
    set etmiyordu). Artık walk-forward döngüsü kendi GERÇEK ardışık kayıp
    sayacını tutuyor — ctx.risk.consecutive_losses her adımda beslendiği
    için DrawdownSizingStage (final_size'ı gerçekten küçültüyor) artık
    burada da devrede. Kill switch'in KENDİSİ (GÜVENLİK: bkz. aşağıdaki
    not) RiskEngine üzerinden DEĞİL, bu döngünün kendi seviyesinde simüle
    ediliyor."""
    engine = engine or CognitiveEngine()

    # GÜVENLİK — kritik, dikkatli okunmalı: RiskEngine._trip_kill_switch()
    # eşiğe ulaşınca app_settings.ai_enabled=false'ı GERÇEKTEN DB'ye yazıyor
    # (persist=False ile atlanmıyor). Bu fonksiyon canlı dashboard'dan
    # (POST /api/v1/backtest/run-real-async) tetiklenebiliyor — ctx.risk.
    # kill_switch_consecutive_losses'a GERÇEK eşiği vermek, bir backtest
    # koşusunun CANLI ai_enabled'ı yanlışlıkla kapatmasına yol açardı.
    # Bunun yerine: gerçek eşik SADECE okunuyor, kill switch'in ETKİSİ
    # (eşiğe ulaşınca yeni pozisyon açmayı durdurma) bu döngünün kendi
    # seviyesinde simüle ediliyor — ctx.risk.kill_switch_consecutive_losses
    # hep varsayılan (0/devre dışı) kalıyor, RiskEngine'in gerçek kill
    # switch dalına asla girilmiyor.
    with SessionFactory.get_session() as session:
        kill_switch_threshold = int(AppSettingsRepository(session).get("kill_switch_consecutive_losses"))

    consecutive_losses = 0
    kill_switch_tripped_at_bar: int | None = None
    bars = _run_coroutine_sync(fetch_real_history(symbol, timeframe, bars_count))
    fee_engine = FeeEngine()
    # Faz 268n — kullanıcı isteği: backtest motoru rötuşu, "slippage
    # modellemesi" eksikti. Önceden entry_price = bars[t].close, exit_price
    # = stop/target'ın TAM teorik seviyesiydi — gerçek bir dolum hiçbir
    # zaman tam o fiyattan olmaz, backtest sonuçları sistematik olarak
    # iyimserdi. simulator/slippage_model.py (Faz 268e'de LONG/SHORT<->BUY/
    # SELL yön hatası düzeltilmiş AYNI modül, canlı orchestrator.py'nin
    # kullandığı) burada da kullanılıyor — entry HER ZAMAN, exit ise SADECE
    # stop_loss'ta (gerçek bir market emri, tetiklenince aleyhte kayar);
    # take_profit önceden oturmuş bir LIMIT emri olduğu için (zaten maker
    # ücret varsayımıyla tutarlı) tam hedef fiyattan dolar, kaymaz.
    slippage_model = SlippageModel()

    # Faz 268d: risk ölçeklendirmesi artık backtest'in KENDİ timeframe'ine
    # göre seçilen bir bar setinden geliyor (ör. 15m sinyal -> 1h risk
    # tabanı), her zaman günlük DEĞİL — bkz. dosya başındaki Faz 268d
    # notu. TEK seferde çekilip (API çağrısı israfı yok), her walk-forward
    # adımında sadece o ana kadar GERÇEKTEN kapanmış bar'ları kullanan
    # _risk_atr_pct_asof ile no-lookahead şekilde dilimleniyor.
    risk_timeframe = _BACKTEST_TIMEFRAME_TO_RISK_TIMEFRAME.get(timeframe, "1d")
    risk_bar_duration = _TIMEFRAME_TO_TIMEDELTA.get(risk_timeframe, timedelta(days=1))
    risk_bars = _run_coroutine_sync(fetch_real_history(symbol, risk_timeframe, 400))

    trades = []
    open_positions_never_closed = 0

    for t in range(lookback, len(bars) - 1):
        if kill_switch_threshold > 0 and consecutive_losses >= kill_switch_threshold:
            if kill_switch_tripped_at_bar is None:
                kill_switch_tripped_at_bar = t
            continue  # gerçek kill switch tetiklenseydi AI dururdu — yeni pozisyon açılmıyor

        window = bars[max(0, t - lookback): t + 1]
        daily_atr_pct = _risk_atr_pct_asof(risk_bars, bars[t].timestamp, risk_bar_duration)
        ctx = _build_backtest_context(symbol, timeframe, window, capital_per_trade, daily_atr_pct=daily_atr_pct)
        ctx.risk.consecutive_losses = consecutive_losses
        result_ctx = engine.run(ctx, persist=False)

        direction = result_ctx.decision.proposed_direction or "WAIT"
        size = result_ctx.decision.final_size or 0.0
        if direction not in ("LONG", "SHORT") or size <= 0:
            continue

        # Faz 268ab: council'in WAIT/red kararı DOKUNULMADI (yukarıdaki
        # continue zaten geçti) — sadece council'in GERÇEK yönlü kararı
        # ters çevriliyor, stop/target/slippage aşağıda bu ters yöne göre
        # tutarlı şekilde yeniden kuruluyor.
        if reverse_direction:
            direction = "SHORT" if direction == "LONG" else "LONG"

        raw_price = bars[t].close
        size_seed = capital_per_trade / raw_price if raw_price else 1.0
        entry_side = "BUY" if direction == "LONG" else "SELL"
        entry_price = slippage_model.apply(raw_price, entry_side, size_seed)

        risk_mag = result_ctx.decision.stop_loss
        reward_mag = result_ctx.decision.take_profit
        if not risk_mag or not reward_mag:
            continue

        # Stop/target mesafeleri GERÇEKTEN doldurulan fiyata göre (raw
        # sinyal fiyatına göre değil) — gerçek bir pozisyonun risk tabanı
        # kendi maliyet bazıdır.
        if direction == "LONG":
            stop_price = entry_price - risk_mag
            target_price = entry_price + reward_mag
        else:
            stop_price = entry_price + risk_mag
            target_price = entry_price - reward_mag

        exit_price, exit_reason, exit_idx = _simulate_real_exit(
            bars, t, direction, stop_price, target_price, max_forward_bars
        )
        if exit_price is None:
            open_positions_never_closed += 1
            continue

        if exit_reason == "stop_loss":
            exit_side = "SELL" if direction == "LONG" else "BUY"
            exit_price = slippage_model.apply(exit_price, exit_side, size_seed)

        if direction == "LONG":
            gross_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            gross_pnl_pct = (entry_price - exit_price) / entry_price

        # Faz 223a: take_profit = maker (%0.02), stop_loss = taker (%0.05).
        exit_is_maker = exit_reason == "take_profit"
        entry_fee_pct = fee_engine.config.taker_rate
        exit_fee_pct = fee_engine.config.maker_rate if exit_is_maker else fee_engine.config.taker_rate
        net_pnl_pct = gross_pnl_pct - entry_fee_pct - exit_fee_pct
        # Faz 268-sonrası — kritik bulgu: bu ÖNCEDEN her zaman sabit
        # capital_per_trade ile çarpıyordu — MetaStage'in Kelly çarpanı ve
        # (bu turda eklenen) DrawdownSizingStage'in küçültmesi `size`
        # (final_size, GERÇEKTEN kaç birim al) üzerinde çalışıyordu ama bu
        # küçültmenin dolar PnL'e HİÇBİR etkisi yoktu — kayıp serisinde
        # boyut küçülse bile backtest hep TAM capital_per_trade riske
        # girmiş gibi hesaplıyordu. Artık gerçekten dolduruma giren
        # notional (size*entry_price) kullanılıyor.
        net_pnl_usd = net_pnl_pct * size * entry_price

        consecutive_losses = consecutive_losses + 1 if net_pnl_pct <= 0 else 0

        if agent_memory is not None:
            opinions = result_ctx.__dict__.get("_last_opinions") or []
            _record_backtest_agent_learning(agent_memory, opinions, symbol, direction, net_pnl_usd)

        # Faz 268-sonrası — kullanıcı önerisi: sadece entry/exit/pnl yetmez,
        # işlem boyunca fiyatın GERÇEK maksimum olumlu/olumsuz hareketini
        # (MAE/MFE) de ölçmeliyiz — "SL çok mu dardı yoksa entry mi
        # kötüydü" ayrımının ilk adımı. bars[t:exit_idx+1] zaten bellekte
        # olan GERÇEK fiyat yolu — ekstra ağ isteği yok. Kasıtlı olarak
        # SADECE ölçüm — hiçbir SL/TP kararını burada değiştirmiyor.
        mae_mfe = compute_mae_mfe(direction, entry_price, bars[t:exit_idx + 1])

        # Faz 268-sonrası: koşullu MAE/MFE dağılımları için entry ANINDA
        # aktif olan rejim/volatilite — ctx.market.features zaten bu
        # pencereden gerçekten hesaplanmıştı (bkz. build_cognitive_
        # context), burada sadece okunuyor, ekstra hesaplama yok.
        entry_features = result_ctx.market.features or {}

        trades.append({
            "symbol": symbol,
            "bar_index": t,
            "direction": direction,
            "confidence": result_ctx.decision.confidence or 0.0,
            "regime": entry_features.get("long_term_trend_regime", "insufficient_data"),
            "volatility_regime": entry_features.get("volatility_regime", "normal"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "net_return_pct": net_pnl_pct,
            "net_pnl_usd": net_pnl_usd,
            "mae_pct": mae_mfe["mae_pct"],
            "mfe_pct": mae_mfe["mfe_pct"],
            "time_to_mae_seconds": mae_mfe["time_to_mae_seconds"],
            "time_to_mfe_seconds": mae_mfe["time_to_mfe_seconds"],
            "win": net_pnl_pct > 0,
            "bars_held": exit_idx - t,
            "entry_time": bars[t].timestamp.isoformat(),
            "exit_time": bars[exit_idx].timestamp.isoformat(),
        })

    return _summarize(
        symbol, timeframe, bars, trades, open_positions_never_closed, capital_per_trade,
        kill_switch_tripped_at_bar=kill_switch_tripped_at_bar,
    )


def _summarize(
    symbol: str, timeframe: str, bars: list[OHLCV], trades: list[dict],
    open_positions_never_closed: int, capital_per_trade: float,
    kill_switch_tripped_at_bar: int | None = None,
) -> dict:
    from collections import Counter

    from analytics.metrics.engine import MetricsEngine

    if not trades:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "num_bars": len(bars),
            "trade_count": 0,
            "open_positions_never_closed": open_positions_never_closed,
            "total_pnl_usd": 0.0,
            "metrics": {},
            "equity_curve": [capital_per_trade],
            "kill_switch_tripped_at_bar": kill_switch_tripped_at_bar,
        }

    wins = sum(1 for t in trades if t["win"])
    total_pnl_usd = sum(t["net_pnl_usd"] for t in trades)
    returns = [t["net_return_pct"] for t in trades]
    equity = [capital_per_trade]
    for t in trades:
        equity.append(equity[-1] + t["net_pnl_usd"])

    metrics = {
        "win_rate": wins / len(trades),
        "avg_return_pct": sum(returns) / len(returns),
        # numpy skalerleri JSON/Postgres JSON kolonuna sessizce yazılamıyor
        # (FastAPI/pydantic serileştirmesi patlıyor) — düz Python float'a
        # çeviriliyor.
        "sharpe_ratio": float(MetricsEngine.sharpe_ratio(returns)),
        "sortino_ratio": float(MetricsEngine.sortino_ratio(returns)),
        "max_drawdown": float(MetricsEngine.max_drawdown(equity)),
        "avg_bars_held": sum(t["bars_held"] for t in trades) / len(trades),
        "exit_reason_distribution": dict(Counter(t["exit_reason"] for t in trades)),
        "open_positions_never_closed": open_positions_never_closed,
        "kill_switch_tripped_at_bar": kill_switch_tripped_at_bar,
    }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "num_bars": len(bars),
        "trade_count": len(trades),
        "open_positions_never_closed": open_positions_never_closed,
        "total_pnl_usd": total_pnl_usd,
        "metrics": metrics,
        "equity_curve": equity,
        "trades": trades,
        "kill_switch_tripped_at_bar": kill_switch_tripped_at_bar,
    }


def run_real_backtest_multi(
    symbols: list[str],
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = DEFAULT_LOOKBACK,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    capital_per_trade: float = 1000.0,
    feed_agent_learning: bool = False,
) -> dict:
    """Birden fazla sembol için ayrı ayrı çalıştırıp birleştirir — her
    sembolün kendi gerçek geçmiş verisi, kendi walk-forward'u var (ortak
    bir zaman ekseni ZORUNLU değil, cognitive_backtest_runner.py'nin
    aksine — o yüzden VectorizedBacktestEngine'in "tüm semboller aynı
    sayıda bar" kısıtına burada gerek yok).

    Faz 248: feed_agent_learning=True ise, her sembolün gerçek simüle
    işlem sonuçları AgentMemory'ye source="backtest" ile kaydedilir.

    Faz 268i — kullanıcı bulgusu: bu, önceden CANLI ile AYNI (varsayılan
    "agent_memory_history/") dosyaya yazıyordu. source="backtest" etiketi
    kaydı görünür/ayırt edilebilir kılıyordu ama HİÇBİR gerçek sorgu
    (WeightOptimizer.propose_weights, AgentMemory.get_summary) bu alana
    göre filtrelemiyordu — yani her backtest çalıştırması, oranı düşük
    olsa da, canlı ağırlık öğrenmesine sessizce karışıyordu. Artık tamamen
    ayrı bir dosyada (backtest_agent_memory_history/) — canlı öğrenmeyi
    hiç etkilemiyor, ama istenirse (ör. meta_optimizer/agent_tuner.py gibi
    offline analizler için) hâlâ ayrıca incelenebilir."""
    from services.agent_memory import AgentMemory

    engine = CognitiveEngine()
    agent_memory = AgentMemory(storage_path="backtest_agent_memory_history") if feed_agent_learning else None
    per_symbol = {}
    for symbol in symbols:
        per_symbol[symbol] = run_real_backtest(
            symbol, timeframe, bars_count, lookback, max_forward_bars, capital_per_trade,
            engine=engine, agent_memory=agent_memory,
        )

    total_pnl_usd = sum(r["total_pnl_usd"] for r in per_symbol.values())
    total_trades = sum(r["trade_count"] for r in per_symbol.values())
    all_trades = [t for r in per_symbol.values() for t in r.get("trades", [])]
    all_wins = sum(1 for t in all_trades if t["win"])

    # Sembol bazlı equity curve'ler kendi bar indekslerine göre — ortak bir
    # zaman ekseni yok. Gerçek, birleşik bir eşitlik eğrisi için tüm
    # işlemleri GERÇEK giriş zamanına göre sıralayıp kümülatif pnl'i
    # hesaplıyoruz — kaç sembol olursa olsun tek, tutarlı bir eğri.
    all_trades_sorted = sorted(all_trades, key=lambda t: t["entry_time"])
    combined_equity = [capital_per_trade * len(symbols)]
    for t in all_trades_sorted:
        combined_equity.append(combined_equity[-1] + t["net_pnl_usd"])

    return {
        "symbols": symbols,
        "timeframe": timeframe,
        "total_trades": total_trades,
        "total_pnl_usd": total_pnl_usd,
        "overall_win_rate": (all_wins / total_trades) if total_trades else 0.0,
        "combined_equity_curve": combined_equity,
        "per_symbol": per_symbol,
    }


def persist_real_backtest_run(result: dict, session, lookback: int = DEFAULT_LOOKBACK):
    """run_real_backtest_multi()'nin çıktısını, mevcut BacktestRun
    contract'ına (Class 2, hiç silinmez) yazıyor — mock backtest'in
    kullandığı AYNI tablo/repository, sadece metrics.mode ile ayırt
    ediliyor."""
    from contracts.backtest_run import BacktestRun
    from contracts.experiment_registry import ExperimentRegistry
    from database.repositories.backtest_run_repository import BacktestRunRepository
    from simulator.fee_engine import FeeEngine

    per_symbol_pnl = {sym: r["total_pnl_usd"] for sym, r in result["per_symbol"].items()}
    per_symbol_metrics = {sym: r["metrics"] for sym, r in result["per_symbol"].items()}
    num_bars = sum(r["num_bars"] for r in result["per_symbol"].values())

    run = BacktestRun(
        symbols=result["symbols"],
        git_sha=ExperimentRegistry.get_git_sha(),
        fee=FeeEngine().config.taker_rate,
        lookback=lookback,
        num_bars=num_bars,
        total_pnl=result["total_pnl_usd"],
        per_symbol_pnl=per_symbol_pnl,
        metrics={
            "mode": "real_historical",
            "timeframe": result["timeframe"],
            "total_trades": result["total_trades"],
            "overall_win_rate": result["overall_win_rate"],
            "per_symbol": per_symbol_metrics,
        },
        equity_curve=result["combined_equity_curve"],
    )
    return BacktestRunRepository(session).save(run)


def run_portfolio_backtest(
    symbols: list[str],
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = DEFAULT_LOOKBACK,
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
    starting_capital: float = 10000.0,
    max_concurrent_positions: int = 5,
    max_capital_pct: float = 0.5,
) -> dict:
    """Faz 268o — kullanıcı isteği: "backtest motoru rötuşu... portföy
    seviyesi backtest." run_real_backtest_multi() her sembolü BAĞIMSIZ
    çalıştırıyordu — her biri KENDİ TAM capital_per_trade'ini kullanıyordu,
    ortak bir sermaye/eşzamanlılık kısıtı yoktu (5 sembolde 5 kat sermaye
    varmış gibi). Burada TEK bir paylaşılan sermaye havuzu ve TEK bir
    max_concurrent_positions limiti üzerinden, TÜM semboller GERÇEKTEN
    aynı anda simüle ediliyor — canlı RiskEngine'in MAX_CONCURRENT_
    POSITIONS/MAX_CAPITAL_PCT kontrolüyle aynı mantık (bkz. engines/
    risk_engine.py). Her adımda ÖNCE açık pozisyonlar kapanma kontrolünden
    geçer (sermaye serbest kalsın), SONRA yeni sinyaller değerlendirilir —
    aynı adımda kapanan bir pozisyonun sermayesi aynı adımda yeni bir
    pozisyona akabilir, tıpkı gerçek zamanlı bir sistemde olacağı gibi.

    Varsayım (dürüstçe belirtilmeli): tüm sembollerin aynı `timeframe`'deki
    bar'larının aynı bar indeksinde aynı gerçek zamana denk geldiği kabul
    ediliyor — büyük Binance USDT çiftleri için mum sınırları global
    olarak hizalıdır (hepsi aynı :00/:15/:30 UTC'de başlar), bu yüzden
    pratikte doğru, ama hiçbir sembolde eksik/boş bar olmadığı varsayımına
    dayanıyor."""
    engine = CognitiveEngine()
    fee_engine = FeeEngine()
    slippage_model = SlippageModel()

    bars_by_symbol: dict[str, list[OHLCV]] = {}
    risk_bars_by_symbol: dict[str, list[OHLCV]] = {}
    risk_duration_by_symbol: dict[str, timedelta] = {}
    for symbol in symbols:
        bars_by_symbol[symbol] = _run_coroutine_sync(fetch_real_history(symbol, timeframe, bars_count))
        risk_timeframe = _BACKTEST_TIMEFRAME_TO_RISK_TIMEFRAME.get(timeframe, "1d")
        risk_bars_by_symbol[symbol] = _run_coroutine_sync(fetch_real_history(symbol, risk_timeframe, 400))
        risk_duration_by_symbol[symbol] = _TIMEFRAME_TO_TIMEDELTA.get(risk_timeframe, timedelta(days=1))

    min_len = min(len(b) for b in bars_by_symbol.values())

    open_positions: list[dict] = []
    closed_trades: list[dict] = []
    open_positions_never_closed = 0
    equity_curve = [starting_capital]
    equity = starting_capital

    for t in range(lookback, min_len - 1):
        # 1) Açık pozisyonların bu adımda kapanıp kapanmadığını ÖNCE
        #    kontrol et — kapananlar sermayeyi yeni girişlerden önce
        #    serbest bırakır.
        still_open = []
        for pos in open_positions:
            bar = bars_by_symbol[pos["symbol"]][t]
            exit_price = None
            exit_reason = None
            if pos["direction"] == "LONG":
                if pos["stop_price"] is not None and bar.low <= pos["stop_price"]:
                    exit_price, exit_reason = pos["stop_price"], "stop_loss"
                elif pos["target_price"] is not None and bar.high >= pos["target_price"]:
                    exit_price, exit_reason = pos["target_price"], "take_profit"
            else:
                if pos["stop_price"] is not None and bar.high >= pos["stop_price"]:
                    exit_price, exit_reason = pos["stop_price"], "stop_loss"
                elif pos["target_price"] is not None and bar.low <= pos["target_price"]:
                    exit_price, exit_reason = pos["target_price"], "take_profit"

            if exit_price is None and (t - pos["entry_idx"]) >= max_forward_bars:
                # Faz 216 ilkesi: vade dolunca kapatma yok — sonsuza dek
                # açık kalmış sayılır, uydurma bir fiyat İCAT EDİLMEZ,
                # sonuçlara dahil edilmez (ama sermayesi de bir daha
                # kullanılamaz — gerçek bir "asla kapanmayan" pozisyonun
                # gerçek maliyeti budur).
                open_positions_never_closed += 1
                continue

            if exit_price is None:
                still_open.append(pos)
                continue

            if exit_reason == "stop_loss":
                exit_side = "SELL" if pos["direction"] == "LONG" else "BUY"
                exit_price = slippage_model.apply(exit_price, exit_side, pos["size_seed"])

            if pos["direction"] == "LONG":
                gross_pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            else:
                gross_pnl_pct = (pos["entry_price"] - exit_price) / pos["entry_price"]

            exit_is_maker = exit_reason == "take_profit"
            entry_fee_pct = fee_engine.config.taker_rate
            exit_fee_pct = fee_engine.config.maker_rate if exit_is_maker else fee_engine.config.taker_rate
            net_pnl_pct = gross_pnl_pct - entry_fee_pct - exit_fee_pct
            net_pnl_usd = net_pnl_pct * pos["notional"]

            equity += net_pnl_usd
            equity_curve.append(equity)
            closed_trades.append({
                "symbol": pos["symbol"],
                "direction": pos["direction"],
                "confidence": pos["confidence"],
                "entry_price": pos["entry_price"],
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "net_return_pct": net_pnl_pct,
                "net_pnl_usd": net_pnl_usd,
                "win": net_pnl_pct > 0,
                "bars_held": t - pos["entry_idx"],
                "entry_time": pos["entry_time"].isoformat(),
                "exit_time": bar.timestamp.isoformat(),
            })

        open_positions = still_open

        # 2) Sonra her sembol için yeni sinyal değerlendir — kapananların
        #    az önce serbest bıraktığı kapasiteyi kullanabilir.
        capital_used = sum(p["notional"] for p in open_positions)
        open_symbols = {p["symbol"] for p in open_positions}
        for symbol in symbols:
            if len(open_positions) >= max_concurrent_positions:
                break
            if symbol in open_symbols:
                continue  # aynı sembolde aynı anda ikinci pozisyon açılmaz

            bars = bars_by_symbol[symbol]
            remaining_slots = max_concurrent_positions - len(open_positions)
            available_capital = starting_capital * max_capital_pct - capital_used
            if available_capital <= 0 or remaining_slots <= 0:
                continue
            capital_per_trade = available_capital / remaining_slots

            window = bars[max(0, t - lookback): t + 1]
            daily_atr_pct = _risk_atr_pct_asof(
                risk_bars_by_symbol[symbol], bars[t].timestamp, risk_duration_by_symbol[symbol]
            )
            ctx = _build_backtest_context(symbol, timeframe, window, capital_per_trade, daily_atr_pct=daily_atr_pct)
            result_ctx = engine.run(ctx, persist=False)

            direction = result_ctx.decision.proposed_direction or "WAIT"
            size = result_ctx.decision.final_size or 0.0
            if direction not in ("LONG", "SHORT") or size <= 0:
                continue

            risk_mag = result_ctx.decision.stop_loss
            reward_mag = result_ctx.decision.take_profit
            if not risk_mag or not reward_mag:
                continue

            raw_price = bars[t].close
            size_seed = capital_per_trade / raw_price if raw_price else 1.0
            entry_side = "BUY" if direction == "LONG" else "SELL"
            entry_price = slippage_model.apply(raw_price, entry_side, size_seed)

            if direction == "LONG":
                stop_price = entry_price - risk_mag
                target_price = entry_price + reward_mag
            else:
                stop_price = entry_price + risk_mag
                target_price = entry_price - reward_mag

            open_positions.append({
                "symbol": symbol,
                "direction": direction,
                "entry_idx": t,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "notional": capital_per_trade,
                "size_seed": size_seed,
                "confidence": result_ctx.decision.confidence or 0.0,
                "entry_time": bars[t].timestamp,
            })
            capital_used += capital_per_trade
            open_symbols.add(symbol)

    return _summarize_portfolio(
        symbols, timeframe, min_len, closed_trades, open_positions_never_closed, starting_capital, equity_curve
    )


def _summarize_portfolio(
    symbols: list[str], timeframe: str, num_bars: int, trades: list[dict],
    open_positions_never_closed: int, starting_capital: float, equity_curve: list[float],
) -> dict:
    from collections import Counter

    from analytics.metrics.engine import MetricsEngine

    if not trades:
        return {
            "symbols": symbols,
            "timeframe": timeframe,
            "num_bars": num_bars,
            "trade_count": 0,
            "open_positions_never_closed": open_positions_never_closed,
            "total_pnl_usd": 0.0,
            "starting_capital": starting_capital,
            "metrics": {},
            "equity_curve": equity_curve,
        }

    wins = sum(1 for t in trades if t["win"])
    total_pnl_usd = sum(t["net_pnl_usd"] for t in trades)
    returns = [t["net_return_pct"] for t in trades]

    metrics = {
        "win_rate": wins / len(trades),
        "avg_return_pct": sum(returns) / len(returns),
        "sharpe_ratio": float(MetricsEngine.sharpe_ratio(returns)),
        "sortino_ratio": float(MetricsEngine.sortino_ratio(returns)),
        "max_drawdown": float(MetricsEngine.max_drawdown(equity_curve)),
        "avg_bars_held": sum(t["bars_held"] for t in trades) / len(trades),
        "exit_reason_distribution": dict(Counter(t["exit_reason"] for t in trades)),
        "open_positions_never_closed": open_positions_never_closed,
        "per_symbol_trade_count": dict(Counter(t["symbol"] for t in trades)),
    }

    return {
        "symbols": symbols,
        "timeframe": timeframe,
        "num_bars": num_bars,
        "trade_count": len(trades),
        "open_positions_never_closed": open_positions_never_closed,
        "total_pnl_usd": total_pnl_usd,
        "starting_capital": starting_capital,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trades": trades,
    }


def persist_portfolio_backtest_run(result: dict, session, lookback: int = DEFAULT_LOOKBACK):
    """run_portfolio_backtest()'in çıktısını persist_real_backtest_run()
    ile AYNI BacktestRun contract'ına yazar — metrics.mode='portfolio' ile
    ayırt edilir, tek sembollü/bağımsız-çoklu-sembol çalıştırmalarla
    karışmaz."""
    from collections import defaultdict

    from contracts.backtest_run import BacktestRun
    from contracts.experiment_registry import ExperimentRegistry
    from database.repositories.backtest_run_repository import BacktestRunRepository

    per_symbol_pnl: dict[str, float] = defaultdict(float)
    for t in result.get("trades", []):
        per_symbol_pnl[t["symbol"]] += t["net_pnl_usd"]

    run = BacktestRun(
        symbols=result["symbols"],
        git_sha=ExperimentRegistry.get_git_sha(),
        fee=FeeEngine().config.taker_rate,
        lookback=lookback,
        num_bars=result["num_bars"],
        total_pnl=result["total_pnl_usd"],
        per_symbol_pnl=dict(per_symbol_pnl),
        metrics={
            "mode": "portfolio",
            "timeframe": result["timeframe"],
            "total_trades": result["trade_count"],
            "overall_win_rate": result["metrics"].get("win_rate", 0.0),
            "starting_capital": result["starting_capital"],
            **result["metrics"],
        },
        equity_curve=result["equity_curve"],
    )
    return BacktestRunRepository(session).save(run)
