"""End-to-end cognitive loop orchestrator — v1.1 trusted paper cycle."""
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from config import get_settings
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from database.repositories.risk_limit_repository import load_active_limits
from market_data.features.signal_engine import (
    compute_daily_atr_pct,
    compute_data_quality_score,
    compute_higher_timeframe_trend,
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from market_data.ingestion.data_provider import OHLCVProvider, get_ohlcv_provider
from market_data.macro.economic_calendar import compute_event_proximity
from ml.training.replay_memory import ReplayMemory
from observability.metrics import decision_pipeline_latency_seconds
from services.cognitive_engine import CognitiveEngine
from services.decision_recorder import DecisionRecorder
from services.forward_outcome import ForwardOutcome
from services.risk_state import load_position_risk_state
from simulator.fill_engine import FillEngine

# Faz 255 performans düzeltmesi: kritik bulgu — canlıda doğrulandı. Risk
# ölçeklendirmesi için kullanılan bar'ları HER trading cycle'da (120s'de
# bir), HER sembol için yeniden çekmek gerçek bir performans regresyonuna
# yol açtı — her cycle sembol başına bir EK Binance isteği eklendi, bu da
# cycle süresini uzatıp trading_cycle sağlık kontrolünün "unhealthy"
# (dakikalarca bayat) düşmesine sebep oldu. Bu bar'lar (1d/4h) zaten
# yavaş değişen bir ölçü — 120 saniyede bir tazelenmesinin hiçbir anlamı
# yok. 15 dakikalık önbellek, riski gerçekçi tutarken gereksiz API
# yükünü ~7x azaltıyor.
#
# Faz 269-sonrası — kullanıcı isteği, gerçek bulgu: yorumun "Tek celery
# worker (-c 1)" varsayımı canlı deployment'ta YANLIŞ çıktı — celery
# worker `-c`/`--concurrency` verilmeden başlatılıyor, bu da varsayılan
# olarak CPU çekirdek sayısı kadar (bu makinede 10) prefork worker
# SÜRECİ demek (doğrulandı: `ps aux` gerçekten 10 ayrı ForkPoolWorker
# PID'i gösterdi). Modül-seviyeli bir dict, fork sonrası her sürecin
# KENDİ ayrı kopyasında yaşar — 10 süreç arasında paylaşılmaz. Sonuç:
# aynı sembol farklı cycle'larda farklı worker'a düşünce (celery'nin
# round-robin dağıtımıyla olağan), önbellek isabet oranı yorumun
# vaat ettiği "~7x azalma"nın çok altında kalıyordu — her süreç
# kendi izole 1/10'luk görünümünü önbellekliyordu. Artık services/
# tasks.py::_CycleLock'un kullandığı AYNI Redis-tabanlı paylaşılan-
# durum deseni: TÜM süreçler AYNI anahtarı paylaşıyor, gerçek bir
# 15-dakikalık pencere TÜM worker'lar için geçerli oluyor. Redis'in
# kendi TTL'i (SETEX) kullanılıyor — elle zaman damgası karşılaştırması
# gerekmiyor.
_RISK_BARS_CACHE_TTL_SECONDS = 900
_RISK_BARS_CACHE_KEY_PREFIX = "risk_bars_cache"


def _serialize_bars(bars: list) -> str:
    return json.dumps([
        {
            "timestamp": bar.timestamp.isoformat(), "open": bar.open, "high": bar.high,
            "low": bar.low, "close": bar.close, "volume": bar.volume,
        }
        for bar in bars
    ])


def _deserialize_bars(raw: str) -> list:
    from market_data.ingestion.ohlcv import OHLCV

    return [
        OHLCV(
            timestamp=datetime.fromisoformat(b["timestamp"]), open=b["open"], high=b["high"],
            low=b["low"], close=b["close"], volume=b["volume"],
        )
        for b in json.loads(raw)
    ]


def _revert_to_wait_if_below_act_threshold(ctx: CognitiveCycleContext, act_threshold: float, reason: str) -> None:
    """Faz 355 — kullanıcı bulgusu (harici mimari inceleme + bağımsız kod
    doğrulaması): _apply_portfolio_fusion'daki iki indirim bloğu (aynı-yönlü
    korelasyon, düşük Effective-Number-of-Bets) SADECE ctx.decision.
    confidence'ı güncelliyordu — final_size'a HİÇ dokunmuyordu (final_size,
    MetaStage'de meta["confidence"]/proposed_size*kelly_multiplier ile TEK
    seferlik hesaplanıp bir daha yeniden türetilmiyordu) VE ACT/REDUCE
    kararı, indirim sonrası confidence act_threshold'un altına düşse bile
    hiç yeniden kontrol edilmiyordu — yorum "sadece boyut küçülüyor"
    diyordu ama gerçekte HİÇBİR ŞEY küçülmüyordu (sadece explain sayfasında
    gösterilen sayı değişiyordu). Bu fonksiyon, indirim sonrası confidence
    artık MetaStage'in ACT kararını verdiği eşiği geçemiyorsa kararı
    dürüstçe WAIT'e çeviriyor (final_size zaten çağıran tarafından aynı
    oranda küçültülmüş oluyor — bkz. iki çağrı noktası)."""
    if ctx.decision.action not in (ActionType.ENTER_LONG, ActionType.ENTER_SHORT, ActionType.REDUCE):
        return
    if (ctx.decision.confidence or 0.0) >= act_threshold:
        return
    ctx.decision.action = ActionType.WAIT
    ctx.decision.final_size = 0.0
    ctx.cognition.relevant_knowledge.append({
        "type": "portfolio_confidence_discount",
        "data": {
            "reason": f"{reason}_dropped_below_act_threshold",
            "confidence": ctx.decision.confidence,
            "act_threshold": act_threshold,
        },
    })


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
    """Redis erişilemezse (ör. kısa bir kesinti) FAIL-OPEN: önbelleksiz
    doğrudan gerçek veriyi çeker — bir yardımcı performans katmanının
    kendisi, asıl veri çekme işlemini asla engellememeli (Binance rate
    limiter/EventLogRepository ile AYNI felsefe)."""
    cache_key = f"{_RISK_BARS_CACHE_KEY_PREFIX}:{symbol}:{timeframe}"
    client = None
    try:
        import redis

        client = redis.from_url(get_settings().REDIS_URL)
        cached_raw = client.get(cache_key)
        if cached_raw:
            return _deserialize_bars(cached_raw)
    except Exception:
        client = None

    bars = data_provider.get_ohlcv(symbol, timeframe, limit=limit) or []

    if client is not None and bars:
        try:
            client.set(cache_key, _serialize_bars(bars), ex=_RISK_BARS_CACHE_TTL_SECONDS)
        except Exception:
            pass

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

    # Faz 269-sonrası — kullanıcı isteği: distributed tracing. cycle_id
    # zaten decisions.id ile AYNI (services/decision_recorder.py) — eksik
    # olan, bu ID'nin log satırlarına hiç yansımamasıydı. Bu sembolün
    # işlendiği süre boyunca (risk red sebepleri, hata logları, pozisyon
    # kapanışı vb.) TÜM log satırları artık otomatik bu cycle_id'yi taşır
    # — bir sonraki sembolün build_cognitive_context çağrısı kendi
    # cycle_id'siyle bunun üzerine yazar (contextvars overwrite, sızıntı
    # yok).
    structlog.contextvars.bind_contextvars(cycle_id=str(ctx.cycle_id), symbol=symbol)

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
        # Faz 316 — kullanıcı bulgusu: kısa-vadeli sinyal hiçbir zaman
        # daha uzun bir zaman dilimiyle karşılaştırılmıyordu. daily_atr_pct
        # ile AYNI, zaten çekilmiş veriyi (ekstra ağ isteği yok) yeniden
        # kullanıyor — bkz. signal_engine.compute_higher_timeframe_trend
        # docstring'i (gerçek ölçüm sonucu ve kaynak/hedef zaman dilimi
        # notu için).
        ctx.market.features["higher_timeframe_trend"] = compute_higher_timeframe_trend(daily_data)

        # Backlog #17 — kullanıcı isteği: "tepeden/dipten kovalıyorsa"
        # giriş engellensin. AYNI zaten-fetch-edilmiş daily_data'dan
        # (ekstra ağ isteği yok) günlük pivot seviyeleri hesaplanıp en
        # yakınına mesafe saklanıyor — decision_recorder.py::record()
        # bunu okuyup (SADECE large-cap'te) gate'e bağlıyor.
        try:
            from analytics.pivot_distance_gate import compute_nearest_pivot_distance_pct
            from market_data.features.signal_engine import compute_pivot_points

            pivots = compute_pivot_points(daily_data)
            pivot_classic = pivots["pivot_classic"] if pivots else None
            ctx.market.features["nearest_pivot_distance_pct"] = compute_nearest_pivot_distance_pct(
                pivot_classic, data[-1].close
            )
        except Exception as exc:
            structlog.get_logger().warning("pivot_distance_computation_failed", error=str(exc))
            ctx.market.features["nearest_pivot_distance_pct"] = None

    # Faz 299-300 — kullanıcı isteği: TP/SL için çok-yöntemli confluence
    # ("zone of agreement" — S/R zone clustering, Volume Profile POC/VA,
    # Pivot Points, Donchian, Keltner). Ölçüm katmanında (services/
    # tp_sl_confluence_gatherer.py) doğrulandı: mevcut ATR-tabanlı hedef
    # gerçek yapısal seviyelere SADECE %2-26 oranında yakın düşüyor —
    # RiskTargetStage burada hesaplanan zone'ları okuyup hedefi (SADECE
    # hedefi, stop'u değil) gerçek bir dirence/desteğe denk geliyorsa
    # daha erken, gerçekçi bir noktaya çekiyor. Hesaplama başarısız
    # olursa (yetersiz veri vb.) fail-closed boş liste — RiskTargetStage
    # bu durumda mevcut ATR hedefini hiç değiştirmeden kullanır.
    try:
        from analytics.tp_sl_confluence import compute_confluence_zones, compute_price_levels

        price_levels = compute_price_levels(data, daily_data, data[-1].close)
        ctx.market.features["confluence_zones"] = compute_confluence_zones(price_levels)
    except Exception as exc:
        structlog.get_logger().warning("confluence_zones_computation_failed", error=str(exc))
        ctx.market.features["confluence_zones"] = []

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
    ctx.risk.starting_capital = risk_state["starting_capital"]
    ctx.risk.ai_enabled = risk_state["ai_enabled"]
    ctx.risk.consecutive_losses = risk_state["consecutive_losses"]
    ctx.risk.kill_switch_consecutive_losses = risk_state["kill_switch_consecutive_losses"]
    ctx.risk.same_direction_open_counts = risk_state["same_direction_open_counts"]
    ctx.risk.max_open_positions_per_symbol_direction = risk_state["max_open_positions_per_symbol_direction"]
    ctx.risk.same_direction_open_notional = risk_state["same_direction_open_notional"]
    ctx.risk.max_same_symbol_direction_capital_pct = risk_state["max_same_symbol_direction_capital_pct"]
    ctx.risk.concept_drift_reason = risk_state["concept_drift_reason"]
    ctx.risk.fixed_position_size_usd = risk_state["fixed_position_size_usd"]

    # Faz 211: her işlem, sermayenin (starting_capital * max_capital_pct)
    # eşit dilimlere bölünmüş (max_concurrent_positions) GERÇEK bir $
    # notional bütçesi hedefliyor; birim sayısı bu bütçenin güncel fiyata
    # bölünmesiyle çıkıyor — pahalı/ucuz varlıklar artık aynı gerçek $
    # riskini taşıyor.
    #
    # Faz 363 — kullanıcı isteği: fixed_position_size_usd > 0 ise bu
    # dinamik formülün YERİNE geçer — her pozisyon (hangi sembol/yön
    # olursa olsun) tam olarak aynı sabit $ notional'ı hedefler. Amaç:
    # PNL değişkenliğini azaltmak ("%86 isabet oranı yakalıyor ama 2k
    # dolar zarar ediyor" — farklı boyutlardaki pozisyonların karışık
    # etkisini ortadan kaldırmak).
    current_price = data[-1].close
    if risk_state["fixed_position_size_usd"] > 0:
        capital_per_trade = risk_state["fixed_position_size_usd"]
    else:
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

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=lookback)
        if not data:
            return None

        # Faz 317-sonrası — kullanıcı kararı: manuel "İşlem vadesi" (Scalp/
        # Gün içi/Swing) seçimi Settings'ten tamamen kaldırıldı. Faz 215'ten
        # beri zaten hiçbir şeyi süreye göre zorla kapatmıyordu (bkz. eski
        # yorum) — geriye kalan tek gerçek işlevi risk (stop/hedef) tabanının
        # hangi bar aralığından geldiğini seçmekti, o da artık sabit 4h
        # (eski "medium" varsayılanı). Gerçek "pozisyona göre esnek ayarlama"
        # zaten Adaptive Barrier Engine'den geliyor (bkz. RiskTargetStage.
        # _try_adaptive_barrier) — bu sabit sadece o mekanizmanın hiç kova
        # bulamadığı durumlardaki statik ATR yedeğinin veri kaynağı.
        risk_timeframe = "4h"
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

        # Faz 317-sonrası — trade_horizon ayarı kaldırıldı (bkz. propose()
        # üstündeki AYNI not), sabit 4h.
        risk_timeframe = "4h"
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
        """Faz 259: önceden portföy VaR füzyonu kasıtlı olarak burada YOK
        idi — "orta-vadeli katman zaten ayrı bir sermaye havuzunda,
        kısa-vadelinin korelasyon/VaR hesabına karışması ekstra bir
        karmaşıklık" gerekçesiyle. Faz 268-sonrası — kullanıcı isteği:
        "tam birleşik portföy VaR'ı" — gerçek risk (drawdown) hangi
        katmanın sermaye muhasebesini kullandığını önemsemez; kısa-
        vadeli VE orta-vadelinin AYNI ANDA açık, birbirine korele
        pozisyonları GERÇEKTE aynı portföyün riskidir. _apply_portfolio_
        fusion artık kısa-vadeli/orta-vadeli ayrımı yapmadan TÜM gerçek
        açık pozisyonları (decision_persistor.py::open_notional_by_
        symbol) kovaryans matrisine dahil ediyor — burada da AYNI
        metodu çağırıyoruz, ayrı bir kopya mantık yerine."""
        proposals: dict[str, dict] = {}
        for sym in symbols:
            p = self.propose_medium_term(sym)
            if p is not None:
                proposals[sym] = p

        directional = {
            sym: p for sym, p in proposals.items()
            if p["direction"] in ("LONG", "SHORT") and (p["ctx"].decision.final_size or 0) > 0
        }
        if len(directional) >= 1:
            self._apply_portfolio_fusion(directional)

        return [
            self.finalize_proposal(proposals[sym], seed=seed) if sym in proposals
            else {"symbol": sym, "direction": "NEUTRAL", "error": "no_data_or_disabled"}
            for sym in symbols
        ]

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

        # Faz 269-sonrası — kullanıcı isteği: distributed tracing'in
        # gerçek log çıktısında görünür olması. build_cognitive_context'in
        # bind ettiği cycle_id'yi (contextvars) taşıyan, bu sembolün
        # işlendiği her cycle'da GERÇEKTEN üretilen tek log satırı —
        # önceden risk red sebepleri sadece dönüş verisinde duruyordu,
        # normal (olaysız) bir cycle'da hiçbir şey loglanmıyordu.
        structlog.get_logger().info(
            "cognitive_cycle_completed",
            direction=direction,
            risk_verdict=ctx.risk.evaluation.verdict if ctx.risk.evaluation else "unknown",
        )

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

        # Faz 387 — kullanıcı isteği: trading cycle performans profillemesi
        # (~12.5dk'lık tam sweep'in nereye gittiğini ölçmek). Saf ölçüm —
        # davranış DEĞİŞMEDİ, sadece sembol başına hangi yolun (cascade/
        # plain) kullanıldığı ve gerçek geçen süre structlog'a düşüyor.
        import time as _time

        import structlog as _structlog

        proposals: dict[str, dict] = {}
        for sym in symbols:
            _t0 = _time.monotonic()
            if ab_test_enabled:
                from services.ab_testing import assign_bucket
                bucket = assign_bucket()
                path = "cascade" if bucket == "treatment" else "plain"
                p = self.propose_multi_timeframe(sym) if bucket == "treatment" else self.propose(sym)
                if p is not None:
                    p["ctx"].cognition.relevant_knowledge.append({
                        "type": "experiment_bucket",
                        "data": {"bucket": f"multi_timeframe_cascade_v1:{bucket}"},
                    })
            else:
                path = "cascade" if cascade_enabled else "plain"
                p = self.propose_multi_timeframe(sym) if cascade_enabled else self.propose(sym)
            _structlog.get_logger().info(
                "symbol_propose_timing",
                symbol=sym, path=path, elapsed_s=round(_time.monotonic() - _t0, 3),
                had_result=p is not None,
            )
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

                # Faz 316-sonrası — kullanıcı isteği: "benched ajan
                # itirazını gölge pozisyon testi." Benching kararının
                # gerçekten doğru olup olmadığını (susturulan bir sinyal
                # boşa mı gidiyor) AYNI izole/etkisiz mekanizmayla ölçer
                # (bkz. services/benched_agent_shadow_tracker.py).
                from services.benched_agent_shadow_tracker import process_symbol_opinions as process_benched_dissent
                process_benched_dissent(sym, p["ctx"], p["data"][-1].close, data_provider=self.data_provider)

        directional = {
            sym: p for sym, p in proposals.items()
            if p["direction"] in ("LONG", "SHORT") and (p["ctx"].decision.final_size or 0) > 0
        }

        # Faz 268-sonrası — kullanıcı isteği: "tam birleşik portföy
        # VaR'ı." _apply_portfolio_fusion artık GERÇEK açık pozisyonları
        # da kovaryans matrisine dahil ediyor (bkz. kendi docstring'i) —
        # bu yüzden tek bir yeni öneri de (zaten açık pozisyonlarla
        # birlikte) anlamlı bir VaR/korelasyon kontrolüne girebiliyor,
        # eskisi gibi "bu cycle'da 2+ eşzamanlı öneri" şartı gerekmiyor.
        if len(directional) >= 1:
            self._apply_portfolio_fusion(directional)

        return [
            self.finalize_proposal(proposals[sym], seed=seed) if sym in proposals
            else {"symbol": sym, "direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}
            for sym in symbols
        ]

    def _apply_portfolio_fusion(self, directional: dict[str, dict]) -> None:
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.repositories.decision_persistor import DecisionPersistor
        from database.session_factory import SessionFactory
        from risk.limits.portfolio import PortfolioRiskEngine
        from services.portfolio_fusion import PortfolioFusionStage

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            starting_capital = float(settings_repo.get("starting_capital"))
            max_var_pct = float(settings_repo.get("max_portfolio_var_pct"))
            # Faz 355 — bkz. _revert_to_wait_if_below_act_threshold docstring'i.
            act_threshold = float(settings_repo.get("act_threshold"))
            existing_notional = DecisionPersistor(session).open_notional_by_symbol()

        returns: dict[str, list[float]] = {}
        proposed_sizes: dict[str, float] = {}
        entry_price_estimates: dict[str, float] = {}
        for sym, p in directional.items():
            closes = [bar.close for bar in p["data"]]
            rets = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes)) if closes[i - 1]
            ]
            if len(rets) < 2:
                continue
            returns[sym] = rets
            # ctx.decision.final_size bu noktada base-varlık MİKTARI
            # (örn. kaç adet VET) — orchestrator.py:287'de
            # capital_per_trade/current_price olarak kuruluyor.
            # PortfolioFusionStage.fuse() ise proposed_sizes'ı "portföy
            # DEĞERİNİN fraksiyonu" (0-1 arası ağırlık) olarak bekliyor
            # (bkz. portfolio_fusion.py docstring'i) — miktarı doğrudan
            # ağırlık gibi VaR hesabına (weights @ cov @ weights) sokmak
            # portfolio_var'ı gerçek dışı şişiriyor, scale-down çarpanı
            # neredeyse sıfıra çöküyor ve HER pozisyon boyutu centin
            # altına düşüyor (gerçek bulgu: notional $0.01-$0.20 arası,
            # olması gereken ~$40-250 yerine). Fusion'a girmeden önce
            # notional'a (miktar*fiyat) çevirip starting_capital'a
            # bölerek gerçek bir ağırlık fraksiyonu üretiyoruz.
            entry_price_estimates[sym] = closes[-1]
            sign = 1.0 if p["direction"] == "LONG" else -1.0
            quantity = p["ctx"].decision.final_size or 0.0
            notional = quantity * entry_price_estimates[sym]
            proposed_sizes[sym] = sign * (notional / starting_capital) if starting_capital else 0.0

        # Faz 268-sonrası — kullanıcı isteği: "orta-vadeli katmanı portföy
        # VaR'ına dahil et... tam birleşik portföy VaR'ı." Öncesinde
        # SADECE bu cycle'daki eşzamanlı YENİ önerilere bakılıyordu — 10
        # dakika önce (ya da orta-vadeli katmandan saatler önce) açılmış
        # büyük, korele bir pozisyon grubu VaR hesabına hiç girmiyordu;
        # tek bir yeni öneri varsa (medium-term'de neredeyse hep böyle)
        # `len(directional)>=2` şartı hiç sağlanmadığı için fusion
        # baştan çalışmıyordu. Artık kısa-vadeli VE orta-vadelinin
        # GERÇEKTEN açık olan net maruziyeti (decision_persistor.py::
        # open_notional_by_symbol, ayrı sermaye havuzu muhasebesinden
        # bağımsız) de AYNI kovaryans matrisine dahil — sadece BAĞLAM
        # olarak: zaten açık pozisyonların boyutu/güveni burada asla
        # geriye dönük değiştirilmiyor, SADECE bu cycle'ın yeni
        # önerilerinin (directional) boyutu/güveni ayarlanıyor. 1h bar'lar
        # _get_risk_bars_cached ile (15 dakikalık önbellek, zaten risk
        # ATR hesabı için kurulu) çekiliyor. GERÇEK canlıda doğrulanan
        # ölçek: 150+ farklı sembolde açık pozisyon var — bunları SIRALI
        # çekmek (152 × ağ gecikmesi) her cycle'a onlarca saniye eklerdi;
        # api/rest/positions.py::_fetch_current_prices'ın AYNI gerçek
        # bulgusuyla (Faz 268w) çözdüğü sorun — ThreadPoolExecutor ile
        # GERÇEKTEN paralel çekiliyor, toplam süre en yavaş TEK isteğe
        # iniyor.
        symbols_needing_bars = [
            row["symbol"] for row in existing_notional
            if row["symbol"] not in returns and starting_capital
        ]
        if symbols_needing_bars:
            from concurrent.futures import ThreadPoolExecutor

            def _fetch_one(sym: str) -> tuple[str, list]:
                try:
                    return sym, _get_risk_bars_cached(self.data_provider, sym, timeframe="1h", limit=100)
                except Exception:
                    return sym, []

            with ThreadPoolExecutor(max_workers=min(len(symbols_needing_bars), 16)) as pool:
                fetched_bars = dict(pool.map(_fetch_one, symbols_needing_bars))

            notional_by_symbol = {row["symbol"]: row["signed_notional"] for row in existing_notional}
            for sym, bars in fetched_bars.items():
                closes = [bar.close for bar in bars]
                rets = [
                    (closes[i] - closes[i - 1]) / closes[i - 1]
                    for i in range(1, len(closes)) if closes[i - 1]
                ]
                if len(rets) < 2:
                    continue
                returns[sym] = rets
                proposed_sizes[sym] = float(notional_by_symbol.get(sym) or 0.0) / starting_capital

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

        # directions artık SADECE bu cycle'ın yeni önerilerini değil,
        # zaten açık pozisyonları da kapsıyor (proposed_sizes'ın işareti
        # üzerinden — pozitif ağırlık=LONG, negatif=SHORT) — korelasyon/
        # ENB hesabı GERÇEK tüm maruziyeti görsün diye.
        directions = {
            sym: (directional[sym]["direction"] if sym in directional else ("LONG" if proposed_sizes[sym] >= 0 else "SHORT"))
            for sym in returns
        }
        conviction_multipliers = compute_same_direction_correlation_discount(returns, directions)
        for sym, multiplier in conviction_multipliers.items():
            # Zaten açık pozisyonlar burada asla geriye dönük değiştirilmiyor
            # — SADECE bu cycle'ın yeni önerilerinin (directional) güveni.
            if sym not in directional:
                continue
            # Faz 355 — karar zaten (ör. daha önceki bir indirim yüzünden)
            # WAIT'e dönmüşse ek indirim/kayıt anlamsız — final_size zaten
            # 0, tekrar tekrar loglamak explain sayfasını gürültüyle doldurur.
            if directional[sym]["ctx"].decision.action not in (ActionType.ENTER_LONG, ActionType.ENTER_SHORT, ActionType.REDUCE):
                continue
            if multiplier < 1.0:
                ctx = directional[sym]["ctx"]
                before = ctx.decision.confidence or 0.0
                ctx.decision.confidence = round(before * multiplier, 4)
                # Kullanıcı bulgusu: explain sayfası tek bir confidence
                # sayısı gösteriyordu, "%74 güvenli bir ajan varken nihai
                # karar neden %28 çıktı" sorusuna hiç cevap vermiyordu —
                # bu indirim MetaStage'in ACT/REDUCE kararını verdiği
                # confidence'tan SONRA uygulanıyor (aksiyon zaten
                # kararlaştırılmış). Artık nedeni ve öncesi/sonrası
                # açıkça kaydediliyor.
                #
                # Faz 355 — kritik bulgu: yukarıdaki yorum "sadece boyut
                # küçülüyor" diyordu ama final_size bu noktaya kadar HİÇ
                # yeniden dokunulmuyordu (bkz. _revert_to_wait_if_below_
                # act_threshold docstring'i) — indirim sadece gösterilen
                # sayıyı değiştiriyordu, gerçek pozisyon boyutunu DEĞİL.
                # Artık final_size da AYNI oranda küçültülüyor, ve indirim
                # sonrası confidence act_threshold'un altına düşerse karar
                # dürüstçe WAIT'e çevriliyor.
                ctx.decision.final_size = round((ctx.decision.final_size or 0.0) * multiplier, 8)
                ctx.cognition.relevant_knowledge.append({
                    "type": "portfolio_confidence_discount",
                    "data": {
                        "reason": "same_direction_correlation",
                        "confidence_before": round(before, 4),
                        "confidence_after": ctx.decision.confidence,
                        "multiplier": round(multiplier, 4),
                    },
                })
                _revert_to_wait_if_below_act_threshold(ctx, act_threshold, "same_direction_correlation")

        # Faz 268-sonrası — Effective Number of Bets tabanlı ek portföy
        # sıkılaştırması BURADAYDI (Faz 382'de en iyi ~3 adayı muaf tutacak
        # şekilde revize edilmişti). Kullanıcı isteği (2026-08-31): "Zaten
        # havuz yapabiliyoruz, ENB indirimine gerek yok" — Pozisyon Havuzu/
        # Max Confidence Modu (services/position_pool.py, aç/kapa
        # `max_confidence_mode_enabled`) zaten "çok korele adaydan en
        # iyilerini seç" ihtiyacını karşılıyor, bu ikinci/her-zaman-açık
        # katman gereksiz/fazladan sıkılaştırma olarak değerlendirildi.
        # Tamamen kaldırıldı — analytics/portfolio_intelligence.py de
        # (tek tüketicisi buydu) artık kullanılmıyor, silindi. Yukarıdaki
        # aynı-yönlü korelasyon indirimi (Cross-Symbol Correlation Filter)
        # DOKUNULMADI, ayrı ve geçerli bir mekanizma.

        fusion = PortfolioFusionStage(PortfolioRiskEngine())
        result = fusion.fuse(
            proposed_sizes=proposed_sizes,
            returns=returns,
            portfolio_value=starting_capital,
            max_var=starting_capital * max_var_pct,
        )

        if result.scaled_down:
            for sym, signed_weight in result.final_sizes.items():
                price = entry_price_estimates.get(sym)
                if not price:
                    continue
                directional[sym]["ctx"].decision.final_size = abs(signed_weight) * starting_capital / price

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
