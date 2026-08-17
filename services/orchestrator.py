"""End-to-end cognitive loop orchestrator — v1.1 trusted paper cycle."""
from datetime import UTC, datetime
from typing import Any

from observability.metrics import decision_pipeline_latency_seconds
from database.repositories.app_settings_repository import TRADE_HORIZON_TO_RISK_TIMEFRAME
from database.repositories.risk_limit_repository import load_active_limits
from services.risk_state import load_position_risk_state
from market_data.ingestion.data_provider import get_ohlcv_provider, OHLCVProvider
from market_data.macro.economic_calendar import compute_event_proximity
from market_data.features.signal_engine import (
    compute_daily_atr_pct,
    compute_data_quality_score,
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from simulator.fill_engine import FillEngine
from ml.training.replay_memory import ReplayMemory
from services.cognitive_engine import CognitiveEngine
from services.forward_outcome import ForwardOutcome
from services.decision_recorder import DecisionRecorder
from config import get_settings
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType

import threading
import time

# Faz 255 performans düzeltmesi: kritik bulgu — canlıda doğrulandı. Risk
# ölçeklendirmesi için kullanılan bar'ları HER trading cycle'da (120s'de
# bir), HER sembol için yeniden çekmek gerçek bir performans regresyonuna
# yol açtı — her cycle sembol başına bir EK Binance isteği eklendi, bu da
# cycle süresini uzatıp trading_cycle sağlık kontrolünün "unhealthy"
# (dakikalarca bayat) düşmesine sebep oldu. Bu bar'lar (1d/4h) zaten
# yavaş değişen bir ölçü — 120 saniyede bir tazelenmesinin hiçbir anlamı
# yok. 15 dakikalık önbellek, riski gerçekçi tutarken gereksiz API
# yükünü ~7x azaltıyor.
# 3. taraf inceleme bulgusu (2.5) — modül-seviyeli dict, kilitsiz. FastAPI
# sync endpoint'leri gerçek OS thread pool'unda çalıştırıyor, yani teorik
# olarak iki eşzamanlı istek check-then-write arasında çakışabilir. Tek
# celery worker (-c 1) ve tek uvicorn sürecinde bugüne kadar gerçek bir
# soruna yol açmadı, ama kilit eklemenin maliyeti sıfıra yakın.
_RISK_BARS_CACHE: dict[tuple[str, str], tuple[float, list]] = {}
_RISK_BARS_CACHE_TTL_SECONDS = 900
_RISK_BARS_CACHE_LOCK = threading.Lock()

# Faz 268-sonrası — Effective Number of Bets tabanlı portföy sıkılaştırması
# (bkz. _apply_portfolio_fusion). analytics/portfolio_intelligence.py'nin
# kendi MIN_SYMBOLS'ünden bağımsız, "ne zaman ek indirim uygulanır" eşiği.
MIN_EFFECTIVE_BETS = 3.0
MAX_ENB_DISCOUNT = 0.5  # en fazla %50 ek indirim


def _observe_decision_latency(symbol: str, last_bar_timestamp: datetime) -> None:
    """Faz 268-sonrası: Latency Monitoring — bkz. observability/metrics.py::
    decision_pipeline_latency_seconds'ın modül docstring'i. Negatif bir
    değer (saat kayması, ileri tarihli sentetik veri) gerçek bir gecikme
    değil — Prometheus histogramını bozmasın diye sessizce atlanıyor."""
    ts = last_bar_timestamp if last_bar_timestamp.tzinfo is not None else last_bar_timestamp.replace(tzinfo=UTC)
    latency = (datetime.now(UTC) - ts).total_seconds()
    if latency >= 0:
        decision_pipeline_latency_seconds.labels(symbol=symbol).observe(latency)


def _get_risk_bars_cached(data_provider, symbol: str, timeframe: str = "1d", limit: int = 30) -> list:
    now = time.time()
    key = (symbol, timeframe)
    with _RISK_BARS_CACHE_LOCK:
        cached = _RISK_BARS_CACHE.get(key)
        if cached and (now - cached[0]) < _RISK_BARS_CACHE_TTL_SECONDS:
            return cached[1]
    bars = data_provider.get_ohlcv(symbol, timeframe, limit=limit) or []
    with _RISK_BARS_CACHE_LOCK:
        _RISK_BARS_CACHE[key] = (now, bars)
    return bars


def _combine_timeframe_beliefs(timeframe_beliefs: dict[str, dict]) -> dict:
    """Faz 268c — Multi-Timeframe Cascade (yol haritası Faz C). Bağımsız
    kanıt varsayımıyla basit Bayesian birleştirme:
    P(LONG | tf1, tf2, ...) ∝ P(LONG|tf1) × P(LONG|tf2) × ... (prior 0.5/0.5).
    WAIT/NEUTRAL diyen bir zaman dilimi hiçbir bilgi vermiyor sayılır —
    çarpıma dahil edilmez (WAIT bir yön tahmini değil, Faz245 ile aynı ilke)."""
    long_product = 1.0
    short_product = 1.0
    informative_count = 0

    for belief in timeframe_beliefs.values():
        direction = belief.get("direction", "NEUTRAL")
        # 0.0/1.0'a hiç yaklaşmayan bir sınır — tek bir zaman diliminin
        # ürünü tamamen sıfırlamasını/domine etmesini engelliyor.
        confidence = max(0.01, min(0.99, belief.get("confidence") or 0.0))
        if direction == "LONG":
            long_product *= confidence
            short_product *= (1 - confidence)
            informative_count += 1
        elif direction == "SHORT":
            short_product *= confidence
            long_product *= (1 - confidence)
            informative_count += 1

    if informative_count == 0:
        return {
            "combined_direction": None, "combined_confidence": 0.0,
            "agreement_count": 0, "total_informative": 0,
        }

    total = long_product + short_product
    p_long = (long_product / total) if total > 0 else 0.5
    p_short = 1 - p_long
    combined_direction = "LONG" if p_long >= p_short else "SHORT"
    combined_confidence = round(max(p_long, p_short), 3)
    agreement_count = sum(
        1 for b in timeframe_beliefs.values() if b.get("direction") == combined_direction
    )

    return {
        "combined_direction": combined_direction,
        "combined_confidence": combined_confidence,
        "agreement_count": agreement_count,
        "total_informative": informative_count,
    }


def _get_daily_bars_cached(data_provider, symbol: str) -> list:
    """Orta-vadeli katman (propose_medium_term) için gerçek günlük bar —
    kısa-vadeli katman artık _get_risk_bars_cached(..., timeframe="4h")
    kullanıyor, bkz. Faz 262 notu."""
    return _get_risk_bars_cached(data_provider, symbol, timeframe="1d")


def build_cognitive_context(
    symbol: str,
    timeframe: str,
    data,
    daily_data=None,
    timeframe_filter: str | None = None,
    exclude_timeframe: str | None = None,
    capital_pct_override: float | None = None,
    max_concurrent_override: int | None = None,
) -> CognitiveCycleContext:
    """Faz 224 review bulgusu (E): bu mantık önceden HEM burada (özel
    _build_context metodu olarak) HEM DE api/rest/cognitive.py'de
    (run_cognitive_cycle içinde) bağımsızca tekrarlanıyordu — "gap #15 ile
    aynı desen: iki entrypoint aynı işi bağımsız yapıyor, biri
    düzeltilince diğeri unutulabiliyor" (Faz 214'ün kendi yorumu, gerçek
    bir örneği: proposed_size düzeltmesi orchestrator.py'de yapılıp
    cognitive.py'de unutulmuştu). Artık TEK gerçek kaynak — her iki
    entrypoint de bunu çağırıyor."""
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = timeframe

    # Kullanıcı isteği: onchain ajanının gerçek sinyali (network_activity_
    # trend/hash_rate_trend/mvrv_zscore) SADECE Bitcoin zincirinden geliyor
    # (bkz. agents/onchain_agent.py::is_btc kontrolü, mvrv_zscore da
    # bitcoin-data.com'dan — BTC'ye özel bir API). Diğer sembollerde
    # exchange_inflow/outflow ve whale sinyalleri de hiç uygulanmıyor
    # (services/context_adapter.py'nin kendi notu) — yani BTC dışındaki
    # her sembolde onchain'in söyleyecek GERÇEK hiçbir şeyi yok. Council'i
    # hiç etkilemesin diye (bkz. data_unavailable_domains — backtest'te
    # aynı mekanizma zaten kör WAIT'lerin total_weight'i şişirdiğini
    # kanıtladı) BTC dışı sembollerde hiç çağrılmıyor.
    if not symbol.upper().startswith("BTC"):
        ctx.market.data_unavailable_domains = ["onchain"]

    # Kritik bulgu (2026-08-05): buradan sadece ham rsi/ema/macd sayıları
    # geçiyordu — TechnicalAgent'ın gerçekten skorladığı trend/momentum/
    # market_structure/ema_alignment/volatility_regime alanlarını HİÇBİR
    # kod üretmiyordu (hep varsayılan/nötr), ve Pattern/Quant ajanları da
    # (bu oturumda eklenen) üretimde tamamen kör çalışıyordu. Artık
    # gerçek OHLCV geçmişinden hesaplanıyor — bkz. market_data/features/
    # signal_engine.py.
    technical_signals = compute_technical_signals(data)
    pattern_signals = compute_pattern_signals(data)
    quant_signals = compute_quant_signals(data)

    ctx.market.features = {**technical_signals, **quant_signals}
    # Faz 268-sonrası: Data Quality Scoring — fiyat spike/wick manipülasyonu
    # tespiti (bkz. signal_engine.compute_data_quality_score'un modül
    # notu). EpistemologyAgent bunu okuyup şüpheli veri varken council'in
    # genel güvenini WAIT'e doğru dengeliyor.
    ctx.market.features["data_quality_score"] = compute_data_quality_score(data)["data_quality_score"]
    # Faz 271-sonrası: Economic Calendar Integration — FOMC/CPI gibi yüksek
    # etkili bir makro yayın yakında (HIGH_IMPACT_WINDOW_HOURS içinde) mi.
    # data_quality_score ile AYNI desen: EpistemologyAgent bunu okuyup
    # olay yakınken council'in genel güvenini WAIT'e doğru dengeliyor.
    ctx.market.features["high_impact_event_imminent"] = compute_event_proximity(
        datetime.now(UTC)
    )["high_impact_event_imminent"]
    # Faz 251: kullanıcı kararı — risk (stop/target) ölçeklendirmesi sinyal
    # zaman diliminden (genelde 1m, gürültü seviyesinde ATR) bağımsız,
    # daha yavaş bir bar setinden türetiliyor (bkz. signal_engine.
    # compute_daily_atr_pct üstündeki not — fonksiyon adı "günlük" ama
    # herhangi bir bar listesi üzerinde çalışır). Faz 262: kısa-vadeli
    # katman (orchestrator.propose) artık buraya 4 saatlik bar veriyor
    # ("scalp" niyetine uygun, saatler-günler içinde sonuçlanan mesafe),
    # orta-vadeli katman (propose_medium_term) gerçek günlük bar veriyor
    # ("sabırlı, nadir, büyük" profil) — aynı feature adı ("daily_atr_pct"),
    # farklı çağıranlar farklı kaynak veriyor. daily_data verilmezse ya da
    # yetersizse None kalır — RiskTargetStage bu durumda fail-closed
    # davranır (stop/target set etmez, DecisionFusion zaten yönlü olmayan/
    # eksik bir kararı WAIT'e çevirir).
    if daily_data:
        ctx.market.features["daily_atr_pct"] = compute_daily_atr_pct(daily_data)
    ctx.market.raw_snapshot = {
        "close": data[-1].close,
        "volume": data[-1].volume,
        "high": data[-1].high,
        "low": data[-1].low,
        # Faz 268-sonrası — kullanıcı bulgusu: her ajan AgentOpinion.
        # freshness'ı SABİT bir varsayılanla (0.85/0.90 gibi) bildiriyordu
        # — gerçek veri yaşı hiç ölçülmüyordu. CouncilStage bu alanı okuyup
        # gerçek bir freshness hesaplıyor (bkz. compute_data_freshness).
        "last_bar_timestamp": data[-1].timestamp.isoformat(),
        **pattern_signals,
    }

    # Faz 268ac — kullanıcı bulgusu: "Predictions'da run cycle yaptığımda
    # gelen features'ta MVRV vs. görünmüyor." Gerçek sebep: OnChainAgent'a
    # giden mvrv_zscore/network_activity_trend/hash_rate_trend (services/
    # context_adapter.py::to_onchain, CouncilStage içinde) kararı GERÇEKTEN
    # etkiliyor ama SADECE oradaki ayrı OnChainContext'te yaşıyordu —
    # ctx.market.features'a (Predictions'ın gösterdiği TEK yer) hiç
    # yansımıyordu. Burada AYRICA (aynı, önbellekli fonksiyonlarla) çekilip
    # features'a ekleniyor — sadece görünürlük için, gerçek skorlama zaten
    # to_onchain() üzerinden aynı şekilde çalışıyordu. mvrv_zscore zaten
    # saatlik önbellekli olduğu için burada da çağırmak ek ağ isteği
    # yaratmıyor (aynı süreç-içi önbelleği paylaşıyor).
    if symbol.upper().endswith(("USDT", "BUSD", "USDC", "FDUSD")):
        from market_data.onchain.onchain_provider import (
            fetch_hash_rate_trend,
            fetch_mvrv_zscore,
            fetch_network_activity_trend,
        )

        mvrv = fetch_mvrv_zscore()
        if mvrv is not None:
            ctx.market.features["mvrv_zscore"] = mvrv
        activity = fetch_network_activity_trend()
        if activity is not None:
            ctx.market.features["network_activity_trend"] = activity
        hash_rate = fetch_hash_rate_trend()
        if hash_rate is not None:
            ctx.market.features["hash_rate_trend"] = hash_rate

    # Gap #15: bu alan önceden boş bir dict'ti, bu yüzden RiskEngine her
    # cycle'ı MISSING_LIMIT ile reddediyordu.
    ctx.risk.limits = load_active_limits()

    # Faz 188: test/live modu + gerçek açık pozisyon sayısı/sermaye
    # yüzdesi — RiskEngine (ön) ve RiskGateStage (son) bunları kullanıyor.
    # Faz 259: orta-vadeli katman kısa-vadeliyle aynı sermaye/pozisyon
    # sayacını paylaşmasın diye (bkz. services/risk_state.py docstring).
    risk_state = load_position_risk_state(
        symbol=symbol,
        timeframe_filter=timeframe_filter,
        exclude_timeframe=exclude_timeframe,
        capital_pct_override=capital_pct_override,
        max_concurrent_override=max_concurrent_override,
    )
    ctx.risk.trading_mode = risk_state["trading_mode"]
    ctx.risk.open_position_count = risk_state["open_position_count"]
    ctx.risk.max_concurrent_positions = risk_state["max_concurrent_positions"]
    ctx.risk.capital_used_pct = risk_state["capital_used_pct"]
    ctx.risk.max_capital_pct = risk_state["max_capital_pct"]
    ctx.risk.seconds_since_last_trade = risk_state["seconds_since_last_trade"]
    ctx.risk.min_seconds_between_trades = risk_state["min_seconds_between_trades"]
    ctx.risk.ai_enabled = risk_state["ai_enabled"]
    ctx.risk.consecutive_losses = risk_state["consecutive_losses"]
    ctx.risk.kill_switch_consecutive_losses = risk_state["kill_switch_consecutive_losses"]
    ctx.risk.same_direction_open_counts = risk_state["same_direction_open_counts"]
    ctx.risk.max_open_positions_per_symbol_direction = risk_state["max_open_positions_per_symbol_direction"]
    ctx.risk.concept_drift_reason = risk_state["concept_drift_reason"]

    # Faz 211: her işlem, sermayenin (starting_capital * max_capital_pct)
    # eşit dilimlere bölünmüş (max_concurrent_positions) GERÇEK bir $
    # notional bütçesi hedefliyor; birim sayısı bu bütçenin güncel fiyata
    # bölünmesiyle çıkıyor — pahalı/ucuz varlıklar artık aynı gerçek $
    # riskini taşıyor.
    current_price = data[-1].close
    capital_per_trade = (
        risk_state["starting_capital"] * risk_state["max_capital_pct"]
        / max(risk_state["max_concurrent_positions"], 1)
    )
    ctx.decision.proposed_size = capital_per_trade / current_price if current_price else 0.0

    return ctx


class CognitiveOrchestrator:
    def __init__(
        self,
        data_provider: OHLCVProvider | None = None,
        max_position_size: float = 1.0,
        max_drawdown: float = 0.15,
        current_drawdown: float = 0.0,
    ):
        self.engine = CognitiveEngine()
        self.fill_engine = FillEngine()
        # Faz 268aa — üçüncü taraf incelemesi bulgusu (P2): kullanıcı
        # Faz 252-253'te RL eğitim döngüsünü ("Replay + Explain kazanç
        # isabetine katkısı yok") kaldırmıştı, ama bu ReplayMemory
        # instance'ı ve finalize_proposal()'daki self.memory.add() çağrısı
        # kalmıştı. Doğrulandı: ml/training/pipeline.py::TrainingPipeline
        # (bu buffer'ın TEK gerçek tüketicisi — .memory/.sample()
        # okuyan) hiçbir üretim kodundan hiç çağrılmıyor, sadece kendi
        # dosyasında tanımlı. Yani bu buffer HER cycle'da dolduruluyor
        # ama hiçbir eğitim asla onu okumuyor — kasıtlı olarak
        # SİLİNMEDİ (api/rest/orchestrator.py::/metrics endpoint'i hâlâ
        # memory_size'ı raporluyor, kaldırmak o endpoint'in yanıt
        # şeklini değiştirir) — sadece durum burada açıkça belgeleniyor,
        # bir sonraki kişi "bu neden hiç kullanılmıyor" diye tekrar
        # araştırmasın.
        self.memory = ReplayMemory(capacity=10000)
        self.forward = ForwardOutcome(bars_forward=10)
        self.recorder = DecisionRecorder()
        self.data_provider = data_provider or get_ohlcv_provider()
        self.max_position_size = max_position_size
        self.max_drawdown_limit = max_drawdown
        self.current_drawdown = current_drawdown

    def propose(self, symbol: str) -> dict | None:
        """Faz 199: 'öner ama henüz açma' — services/portfolio_fusion.py'yi
        gerçekten bağlamak için run_cycle()'dan ayrıldı. Birden fazla
        sembolün eşzamanlı önerisini GERÇEKTEN açmadan önce portföy-seviyesi
        VaR'a göre ölçeklendirebilmek gerekiyor (bkz. run_portfolio_aware_
        cycle) — run_cycle() hâlâ tek-sembol, anında-finalize eski
        davranışını koruyor, regresyon yok."""
        # Faz 214: kullanıcı isteği — mum aralığı/geçmiş pencere artık
        # sabit değil, app_settings'ten okunuyor (varsayılan öncekiyle
        # birebir aynı: 1m, 100 bar — regresyon yok).
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            timeframe = settings_repo.get("candle_timeframe")
            lookback = int(settings_repo.get("candle_lookback"))
            # Faz 259: orta-vadeli katman devredeyse, kısa-vadeli katman
            # kendi sermaye/pozisyon sayacından o katmanın pozisyonlarını
            # hariç tutmalı — ikisi aynı kapasiteyi paylaşmasın diye
            # (bkz. services/risk_state.py).
            medium_term_enabled = settings_repo.get("medium_term_enabled") == "true"
            medium_term_timeframe = settings_repo.get("medium_term_timeframe")
            # Faz 265 — kullanıcı isteği: "İşlem vadesi" (Scalp/Gün içi/
            # Swing) artık hiçbir şeyi zorla kapatmıyor (Faz 215) ama YİNE
            # DE gerçek bir anlamı olsun istedi — artık kısa-vadeli
            # katmanın risk (stop/hedef) tabanını hangi bar aralığından
            # aldığını seçiyor. Dar taban (1h) = küçük mesafe = saatler
            # içinde sonuçlanma eğilimi ("scalp"); geniş taban (1d) =
            # büyük mesafe = günler/haftalar ("swing") — ama hiçbiri süre
            # yüzünden zorla kapatılmıyor, sadece gerçekten ulaşınca.
            trade_horizon = settings_repo.get("trade_horizon")

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=lookback)
        if not data:
            return None

        # Faz 262/265: risk (stop/hedef) tabanı artık trade_horizon'a göre
        # seçilen bar aralığından geliyor — aynı 1:4 oran (kalibrasyon için
        # hâlâ gerekli, bkz. RiskTargetStage) artık kullanıcının seçtiği
        # ölçeğe uygulanıyor. Orta-vadeli katman (propose_medium_term) hâlâ
        # gerçek günlük bar kullanıyor — "sabırlı, nadir, büyük" profil
        # orada kalmalı, bu ayardan etkilenmiyor.
        risk_timeframe = TRADE_HORIZON_TO_RISK_TIMEFRAME.get(trade_horizon, "4h")
        risk_data = _get_risk_bars_cached(self.data_provider, symbol, timeframe=risk_timeframe, limit=60)

        ctx = self._build_context(
            symbol,
            timeframe,
            data,
            daily_data=risk_data,
            exclude_timeframe=medium_term_timeframe if medium_term_enabled else None,
        )
        ctx = self.engine.run(ctx, persist=False)
        _observe_decision_latency(symbol, data[-1].timestamp)

        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0

        if direction != "NEUTRAL" and size > 0:
            result = self.fill_engine.simulate({"direction": direction, "size": size}, market_price)
            filled_price, fee = result.filled_price, result.fee
        else:
            filled_price, fee = market_price, 0.0

        # Faz 187: filled_price'ı ctx'e yaz ki RecordingStage (finalize()
        # içinde) gerçek entry_price'ı persist edebilsin.
        ctx.decision.filled_price = filled_price

        return {"ctx": ctx, "data": data, "fee": fee, "direction": direction}

    def propose_multi_timeframe(self, symbol: str, timeframes: list[str] | None = None) -> dict | None:
        """Faz 268c — "İsabeti artırmanın yolu daha akıllı kullanım" yol
        haritasının Faz C'si (Multi-Timeframe Cascade). Rapor: "1m LONG +
        15m LONG + 1h LONG üçlüsü, yalnızca 1m LONG'dan çok daha güçlü bir
        konviksiyon demektir — şu an bu bilgi Council'a hiç ulaşmıyor."

        propose()'un aynısı (birincil karar, GERÇEKTEN açılan pozisyon
        buradan gelir) — TEK fark: council'e geçmeden ÖNCE, üst zaman
        dilimlerinde (varsayılan 15m/1h) çalıştırılan AYRI, TAM
        CognitiveEngine geçişlerinden (embedding dahil) çıkan yönler
        Bayesian olarak birleştirilip ctx.cognition.relevant_knowledge'a
        "timeframe_belief" olarak ekleniyor — Metacognition.evaluate_
        confidence() bunu okuyup birincil yönle UYUŞUYORSA confidence'ı
        yukarı, ÇELİŞİYORSA aşağı çekiyor (bkz. o metodun docstring'i).

        Kullanıcı kararı: raporun önerdiği TAM versiyon — üst zaman
        dilimleri de gerçek council çalıştırıyor, deterministik/ucuz bir
        yaklaşım değil. Bilinçli maliyet: sembol başına ~3 kat CognitiveEngine
        çağrısı. Bu yüzden varsayılan KAPALI (app_settings.multi_timeframe_
        cascade_enabled) — medium_term_enabled ile aynı opt-in desen."""
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            primary_timeframe = settings_repo.get("candle_timeframe")
            lookback = int(settings_repo.get("candle_lookback"))
            medium_term_enabled = settings_repo.get("medium_term_enabled") == "true"
            medium_term_timeframe = settings_repo.get("medium_term_timeframe")
            trade_horizon = settings_repo.get("trade_horizon")
            cascade_timeframes_raw = settings_repo.get("multi_timeframe_cascade_timeframes")

        if timeframes is None:
            timeframes = [tf.strip() for tf in cascade_timeframes_raw.split(",") if tf.strip()]

        # 1. Üst zaman dilimleri — bunlar hiçbir zaman kendi başlarına
        #    pozisyon açmaz, sadece "kaç zaman diliminde de aynı yön
        #    teyit ediliyor" bilgisini üretir. Basit, sabit bir risk
        #    tabanı (4h) yeterli — bu koşuların stop/target'ı hiç
        #    kullanılmıyor, sadece proposed_direction/confidence okunuyor.
        timeframe_beliefs: dict[str, dict] = {}
        for tf in timeframes:
            if tf == primary_timeframe:
                continue
            data_tf = self.data_provider.get_ohlcv(symbol, tf, limit=lookback)
            if not data_tf:
                continue
            risk_data_tf = _get_risk_bars_cached(self.data_provider, symbol, timeframe="4h", limit=60)
            ctx_tf = self._build_context(symbol, tf, data_tf, daily_data=risk_data_tf)
            ctx_tf = self.engine.run(ctx_tf, persist=False)
            timeframe_beliefs[tf] = {
                "direction": ctx_tf.decision.proposed_direction or "NEUTRAL",
                "confidence": ctx_tf.decision.confidence or 0.0,
            }

        combined = _combine_timeframe_beliefs(timeframe_beliefs)

        # 2. Birincil zaman dilimi — propose() ile AYNI mantık, tek fark
        #    aşağıdaki relevant_knowledge enjeksiyonu, engine.run()'dan ÖNCE.
        data = self.data_provider.get_ohlcv(symbol, primary_timeframe, limit=lookback)
        if not data:
            return None

        risk_timeframe = TRADE_HORIZON_TO_RISK_TIMEFRAME.get(trade_horizon, "4h")
        risk_data = _get_risk_bars_cached(self.data_provider, symbol, timeframe=risk_timeframe, limit=60)

        ctx = self._build_context(
            symbol,
            primary_timeframe,
            data,
            daily_data=risk_data,
            exclude_timeframe=medium_term_timeframe if medium_term_enabled else None,
        )
        ctx.cognition.relevant_knowledge.append({
            "type": "timeframe_belief",
            "data": {"per_timeframe": timeframe_beliefs, **combined},
        })
        ctx = self.engine.run(ctx, persist=False)
        _observe_decision_latency(symbol, data[-1].timestamp)

        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0

        if direction != "NEUTRAL" and size > 0:
            result = self.fill_engine.simulate({"direction": direction, "size": size}, market_price)
            filled_price, fee = result.filled_price, result.fee
        else:
            filled_price, fee = market_price, 0.0

        ctx.decision.filled_price = filled_price

        return {"ctx": ctx, "data": data, "fee": fee, "direction": direction}

    def propose_medium_term(self, symbol: str) -> dict | None:
        """Faz 259: kullanıcı isteği — "predictions WAIT döndüğünde uygun
        zamanda ai büyük pozisyonlara girsin, orta vadeli, günler/haftalar
        sürecek işlemlere... daha temkinli daha sakin yaklaşan fakat
        harekete geçtiğinde büyük oynayan bir yapı." Kısa-vadeli propose()
        ile AYNI CognitiveEngine/9-ajan konseyini kullanır — sadece sinyal
        verisi kısa-vadelinin candle_timeframe'i (genelde dakikalar)
        yerine kullanıcının seçtiği günlük/4 saatlik bardan geliyor, ve
        sermaye/pozisyon sayacı kısa-vadeliden tamamen ayrı (timeframe_
        filter/capital_pct_override/max_concurrent_override — bkz.
        services/risk_state.py). "WAIT döndüğünde" kısıtı burada
        UYGULANMIYOR — bu katman kendi bağımsız sinyaliyle çalışıyor,
        kısa-vadeli katmanın o an ne dediğine bakmıyor (ikisi zaten farklı
        zaman dilimlerinden farklı sinyaller üretiyor, birbirini
        bilerek/isteyerek bloke etmesi gerekmiyor)."""
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            if settings_repo.get("medium_term_enabled") != "true":
                return None
            timeframe = settings_repo.get("medium_term_timeframe")
            capital_pct = float(settings_repo.get("medium_term_capital_pct"))
            max_concurrent = int(settings_repo.get("medium_term_max_concurrent"))
            lookback = int(settings_repo.get("candle_lookback"))

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=lookback)
        if not data:
            return None

        # Sinyal zaten günlük/4h'den geliyor ama RiskTargetStage risk
        # ölçeklendirmesini HER ZAMAN gerçek günlük ATR'den yapıyor (bkz.
        # build_cognitive_context üstündeki not) — timeframe zaten "1d"
        # ise aynı barları tekrar çekmeye gerek yok.
        daily_data = data if timeframe == "1d" else _get_daily_bars_cached(self.data_provider, symbol)

        ctx = self._build_context(
            symbol,
            timeframe,
            data,
            daily_data=daily_data,
            timeframe_filter=timeframe,
            capital_pct_override=capital_pct,
            max_concurrent_override=max_concurrent,
        )
        ctx = self.engine.run(ctx, persist=False)
        _observe_decision_latency(symbol, data[-1].timestamp)

        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0

        if direction != "NEUTRAL" and size > 0:
            result = self.fill_engine.simulate({"direction": direction, "size": size}, market_price)
            filled_price, fee = result.filled_price, result.fee
        else:
            filled_price, fee = market_price, 0.0

        ctx.decision.filled_price = filled_price

        return {"ctx": ctx, "data": data, "fee": fee, "direction": direction}

    def run_medium_term_cycle(self, symbols: list[str], seed: int = 42) -> list[dict[str, Any]]:
        """Faz 259: portföy VaR füzyonu (run_portfolio_aware_cycle) kasıtlı
        olarak burada YOK — orta-vadeli katman zaten ayrı bir sermaye
        havuzunda, kısa-vadelinin korelasyon/VaR hesabına karışması ekstra
        bir karmaşıklık, ilk sürümde gerekli değil."""
        results = []
        for sym in symbols:
            p = self.propose_medium_term(sym)
            if p is None:
                results.append({"symbol": sym, "direction": "NEUTRAL", "error": "no_data_or_disabled"})
                continue
            results.append(self.finalize_proposal(p, seed=seed))
        return results

    def finalize_proposal(self, proposal: dict, seed: int = 42) -> dict[str, Any]:
        """propose()'un çıktısını (portföy fusion varsa ctx.decision.
        final_size değişmiş olabilir) al, gerçekten kaydet/aç. run_cycle()
        ile aynı sözlük şeklini döndürür."""
        ctx = proposal["ctx"]
        data = proposal["data"]
        fee = proposal["fee"]
        direction = proposal["direction"]
        filled_price = ctx.decision.filled_price
        size = ctx.decision.final_size or 0.0

        # Faz 268t — kritik bulgu: bu anlık "n-bar forward" hesaplaması
        # ÖNCEDEN iki amaca hizmet ediyordu — ctx.outcome (TradeOutcome)
        # CognitiveEngine.finalize()'ın memory_engine'i tetiklemesi için
        # okunuyordu. Faz 268j (episodic hafızanın sahte ForwardOutcome
        # ile kirlenmesini kapatan düzeltme) finalize()'daki memory_engine.
        # execute(ctx) çağrısını kaldırdığından beri ctx.outcome'ın TEK
        # okuyucusu gitti — artık hiçbir yerde okunmuyor (doğrulandı: grep
        # ile RecordingStage/_persist_and_learn/finalize()'ın hiçbiri
        # ctx.outcome'a bakmıyor). `outcome` (yerel değişken, ctx.outcome
        # DEĞİL) hâlâ gerçek bir tüketicisi olan ReplayMemory (self.memory.
        # add, aşağıda) için hesaplanmaya devam ediyor — o yüzden
        # self.forward.calculate() çağrısının kendisi silinmedi, sadece
        # artık hiç okunmayan ctx.outcome=TradeOutcome(...) ataması
        # kaldırıldı.
        #
        # decisions.status/entry_price/exit_price/opened_at/closed_at,
        # Faz 187'nin GERÇEK, zaman-bazlı pozisyon yaşam döngüsü — bu
        # yukarıdaki n-bar proxy'den kasıtlı olarak bağımsız: decisions.
        # outcome kolonu kayıt anında hep boş kalır (DecisionRecorder),
        # pozisyon gerçekten services/position_closer.py ile kapanana
        # kadar.
        outcome = self.forward.calculate(filled_price, direction, data)
        pnl = outcome["pnl"] - fee
        win = outcome["win"]

        # Memory (sadece risk-onaylı)
        ctx = self.engine.finalize(ctx)

        # Faz 268aa — üçüncü taraf incelemesi bulgusu (P2, savunmacı
        # programlama): final_size zaten DecisionFusion/RiskGateStage
        # reddettiğinde 0'a çekiliyor, bu yüzden `size > 0` pratikte
        # ctx.decision.action == WAIT durumunu da kapsıyor. Ama bu örtük
        # bir bağımlılık — gelecekte bir refactor final_size=0 atamasını
        # unutursa, risk reddine rağmen ReplayMemory'ye "gerçek" bir
        # işlem gibi kayıt düşebilirdi. action'ı ayrıca kontrol etmek,
        # bu iki sinyalin (final_size VE action) İKİSİNİN de reddi doğru
        # yansıtmasını zorunlu kılıyor.
        if direction != "NEUTRAL" and size > 0 and ctx.decision.action != ActionType.WAIT:
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if win else 0,
                "pnl": pnl,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "direction": direction,
            })

        return {
            "direction": direction,
            "size": size,
            "filled_price": filled_price,
            "fee": fee,
            "pnl": pnl,
            "win": win,
            "memory_size": len(self.memory.memory),
            "risk_verdict": ctx.risk.evaluation.verdict if ctx.risk.evaluation else "unknown",
            # Faz 268x — kullanıcı bulgusu: Predictions sayfasında "Risk
            # Verdict" altında code='...' message='...' severity='...'
            # gibi ham Pydantic __str__() çıktısı görünüyordu — str(r)
            # RiskReason nesnesinin kendisini stringe çeviriyordu, insan
            # tarafından okunabilir bir mesaj değil. Sadece gerçek mesajı
            # (kod öneki ile, hangi kural olduğu belli olsun diye) veriyoruz.
            "risk_reasons": (
                [f"{r.code}: {r.message}" for r in ctx.risk.evaluation.reasons]
                if ctx.risk.evaluation else []
            ),
            "action": ctx.decision.action.value if ctx.decision.action else "WAIT",
            "confidence": ctx.decision.confidence,
            "features": ctx.market.features,
            "symbol": ctx.market.symbol,
        }

    def run_portfolio_aware_cycle(self, symbols: list[str], seed: int = 42) -> list[dict[str, Any]]:
        """Faz 199: services/portfolio_fusion.py + risk/limits/portfolio.py'yi
        (yazılmış, test edilmiş ama hiçbir yerden çağrılmayan portföy VaR
        motoru) gerçekten bağlıyor. Aynı cycle'da 2+ sembol eşzamanlı yönlü
        öneri üretirse, GERÇEKTEN açılmadan önce gerçek kovaryans matrisiyle
        (korelasyon dahil) hesaplanan portföy VaR'ı kullanıcının belirlediği
        sınırı (max_portfolio_var_pct) aşarsa önerilen büyüklükler orantılı
        şekilde küçültülüyor — "sinyal limitleri gevşetemez" kuralı burada
        da geçerli, sadece küçültebiliyor.

        Faz 268c — Multi-Timeframe Cascade varsayılan kapalı (app_settings.
        multi_timeframe_cascade_enabled) — açıksa propose() yerine
        propose_multi_timeframe() kullanılır (sembol başına ~3 kat
        CognitiveEngine maliyeti, kullanıcı kararıyla kabul edildi).

        Faz 250 — Live A/B Testing Framework: multi_timeframe_cascade_
        ab_test_enabled açıksa, statik açık/kapalı anahtarı yerine HER
        sembol bağımsız olarak rastgele control (cascade kapalı)/treatment
        (cascade açık) kovasına atanır ve kararı decisions.experiment_
        bucket'a etiketlenir — services/ab_testing.py::evaluate_experiment
        gerçek kapanmış işlemlerle karşılaştırabilsin diye. Varsayılan
        kapalı, açıkken de statik ayarı GEÇERSİZ KILAR (ikisi aynı anda
        anlamsız olurdu)."""
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            cascade_enabled = settings_repo.get("multi_timeframe_cascade_enabled") == "true"
            ab_test_enabled = settings_repo.get("multi_timeframe_cascade_ab_test_enabled") == "true"

        proposals: dict[str, dict] = {}
        for sym in symbols:
            if ab_test_enabled:
                from services.ab_testing import assign_bucket
                bucket = assign_bucket()
                p = self.propose_multi_timeframe(sym) if bucket == "treatment" else self.propose(sym)
                if p is not None:
                    p["ctx"].cognition.relevant_knowledge.append({
                        "type": "experiment_bucket",
                        "data": {"bucket": f"multi_timeframe_cascade_v1:{bucket}"},
                    })
            else:
                p = self.propose_multi_timeframe(sym) if cascade_enabled else self.propose(sym)
            if p is not None:
                proposals[sym] = p
                # Shadow Mode (Faz 268-sonrası) — kullanıcıyla üzerinde
                # anlaşılan 3 seçenekten A: macro'nun bu cycle'da GERÇEKTEN
                # ne dediğini (council'in final kararından bağımsız) izole
                # bir gölge pozisyon olarak kaydet. Council'in kendi
                # kararını asla etkilemez, hata olursa sessizce yutulur
                # (bkz. macro_shadow_tracker.py docstring'i).
                from services.macro_shadow_tracker import process_symbol_opinion
                process_symbol_opinion(sym, p["ctx"], p["data"][-1].close, data_provider=self.data_provider)

        directional = {
            sym: p for sym, p in proposals.items()
            if p["direction"] in ("LONG", "SHORT") and (p["ctx"].decision.final_size or 0) > 0
        }

        if len(directional) >= 2:
            self._apply_portfolio_fusion(directional)

        return [
            self.finalize_proposal(proposals[sym], seed=seed) if sym in proposals
            else {"symbol": sym, "direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}
            for sym in symbols
        ]

    def _apply_portfolio_fusion(self, directional: dict[str, dict]) -> None:
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory
        from risk.limits.portfolio import PortfolioRiskEngine
        from services.portfolio_fusion import PortfolioFusionStage

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            starting_capital = float(settings_repo.get("starting_capital"))
            max_var_pct = float(settings_repo.get("max_portfolio_var_pct"))

        returns: dict[str, list[float]] = {}
        proposed_sizes: dict[str, float] = {}
        for sym, p in directional.items():
            closes = [bar.close for bar in p["data"]]
            rets = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes)) if closes[i - 1]
            ]
            if len(rets) < 2:
                continue
            returns[sym] = rets
            sign = 1.0 if p["direction"] == "LONG" else -1.0
            proposed_sizes[sym] = sign * (p["ctx"].decision.final_size or 0.0)

        if len(returns) < 2:
            return

        min_len = min(len(v) for v in returns.values())
        returns = {s: v[-min_len:] for s, v in returns.items()}
        proposed_sizes = {s: v for s, v in proposed_sizes.items() if s in returns}

        # Faz 268-sonrası — Cross-Symbol Correlation Filter: aşağıdaki VaR
        # tabanlı fusion zaten pozisyon BÜYÜKLÜĞÜNÜ küçültüyor, ama
        # council'in kendi CONVICTION'ı (confidence) hiç etkilenmiyordu.
        # Aynı anda aynı yönde önerilen, birbirine yüksek korele semboller
        # (aynı temel piyasa beta'sının yansımaları, bağımsız kanıt değil)
        # için confidence da gerçekten indirime uğruyor — belief_engine.py'
        # nin tek sembol içindeki crowding_penalty'siyle AYNI ilke, sembol
        # düzeyine taşınmış hali.
        from risk.cross_symbol_correlation import compute_same_direction_correlation_discount

        directions = {sym: directional[sym]["direction"] for sym in returns}
        conviction_multipliers = compute_same_direction_correlation_discount(returns, directions)
        for sym, multiplier in conviction_multipliers.items():
            if multiplier < 1.0:
                ctx = directional[sym]["ctx"]
                before = ctx.decision.confidence or 0.0
                ctx.decision.confidence = round(before * multiplier, 4)
                # Kullanıcı bulgusu: explain sayfası tek bir confidence
                # sayısı gösteriyordu, "%74 güvenli bir ajan varken nihai
                # karar neden %28 çıktı" sorusuna hiç cevap vermiyordu —
                # bu indirim MetaStage'in ACT/REDUCE kararını verdiği
                # confidence'tan SONRA uygulanıyor (aksiyon zaten
                # kararlaştırılmış, sadece boyut/gösterilen güven küçülüyor).
                # Artık nedeni ve öncesi/sonrası açıkça kaydediliyor.
                ctx.cognition.relevant_knowledge.append({
                    "type": "portfolio_confidence_discount",
                    "data": {
                        "reason": "same_direction_correlation",
                        "confidence_before": round(before, 4),
                        "confidence_after": ctx.decision.confidence,
                        "multiplier": round(multiplier, 4),
                    },
                })

        # Faz 268-sonrası — kullanıcının paylaştığı bir incelemeyi
        # doğrularken bulunan gerçek bulgu: yukarıdaki aynı-yönlü
        # korelasyon indirimi TEK bir sembolün eşlerine bakıyor, ama
        # PORTFÖYÜN GENEL çeşitlendirme kalitesini (Effective Number of
        # Bets — analytics/portfolio_intelligence.py, Cognitive Core 2.0/
        # M6) hiç ölçmüyordu: 10 sembol aynı anda önerilse bile hepsi
        # birbirine yüksek korele ise bu gerçekte ~1-2 bağımsız bahis
        # kadar riskli olabilir. Kasıtlı olarak SADECE sıkılaştırma (AI
        # kendi risk limitini asla genişletemez ilkesiyle tutarlı) — ENB
        # düşükken TÜM önerilen sembollere ek bir confidence indirimi
        # uygular, hiçbir zaman artırmaz.
        from analytics.portfolio_intelligence import compute_effective_number_of_bets

        enb_result = compute_effective_number_of_bets(proposed_sizes, returns)
        if enb_result is not None and enb_result["effective_number_of_bets"] < MIN_EFFECTIVE_BETS:
            shortfall = (MIN_EFFECTIVE_BETS - enb_result["effective_number_of_bets"]) / MIN_EFFECTIVE_BETS
            shortfall = min(max(shortfall, 0.0), 1.0)
            enb_multiplier = 1.0 - shortfall * MAX_ENB_DISCOUNT
            for sym in returns:
                ctx = directional[sym]["ctx"]
                before = ctx.decision.confidence or 0.0
                ctx.decision.confidence = round(before * enb_multiplier, 4)
                ctx.cognition.relevant_knowledge.append({
                    "type": "portfolio_confidence_discount",
                    "data": {
                        "reason": "low_effective_number_of_bets",
                        "confidence_before": round(before, 4),
                        "confidence_after": ctx.decision.confidence,
                        "multiplier": round(enb_multiplier, 4),
                        "effective_number_of_bets": enb_result["effective_number_of_bets"],
                    },
                })

        fusion = PortfolioFusionStage(PortfolioRiskEngine())
        result = fusion.fuse(
            proposed_sizes=proposed_sizes,
            returns=returns,
            portfolio_value=starting_capital,
            max_var=starting_capital * max_var_pct,
        )

        if result.scaled_down:
            for sym, signed_size in result.final_sizes.items():
                directional[sym]["ctx"].decision.final_size = abs(signed_size)

    def _build_context(
        self,
        symbol: str,
        timeframe: str,
        data,
        daily_data=None,
        timeframe_filter: str | None = None,
        exclude_timeframe: str | None = None,
        capital_pct_override: float | None = None,
        max_concurrent_override: int | None = None,
    ) -> CognitiveCycleContext:
        # Faz 224 review (E): gövde module-level build_cognitive_context()'e
        # taşındı — api/rest/cognitive.py da artık AYNI fonksiyonu çağırıyor,
        # iki bağımsız kopya kalmadı.
        return build_cognitive_context(
            symbol,
            timeframe,
            data,
            daily_data=daily_data,
            timeframe_filter=timeframe_filter,
            exclude_timeframe=exclude_timeframe,
            capital_pct_override=capital_pct_override,
            max_concurrent_override=max_concurrent_override,
        )

    def run_cycle(self, seed: int = 42, symbol: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        symbol = symbol or settings.DEFAULT_SYMBOL

        proposal = self.propose(symbol)
        if proposal is None:
            return {"direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}

        return self.finalize_proposal(proposal, seed=seed)
