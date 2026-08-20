"""Faz 268-sonrası — kullanıcı isteği: kısa vadeli trend gücü (ADX) düşük
VE uzun vadeli rejim (200-EMA tabanlı) belirsizken (transition) pozisyon
açma. Gerçek 2990 kararlık geçmiş veriyle doğrulandı: bu ikisi aynı anda
sadece %2.4 oranında oluşuyor — geniş bir kesim değil, nadir ve anlamlı
bir "net yön yok" durumu."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import MetaStage


def _long_belief() -> Belief:
    return Belief(
        direction="LONG", strength=0.95, uncertainty=0.0,
        cluster_disagreement=0.0, cluster_balance=1.0, crowding_penalty=0.0,
    )


def _supportive_opinions() -> list[AgentOpinion]:
    opinions = []
    for domain in (AgentDomain.MACRO, AgentDomain.TECHNICAL, AgentDomain.QUANT):
        o = AgentOpinion(domain=domain, direction="LONG", confidence=0.8)
        o.effective_influence = 0.6
        opinions.append(o)
    return opinions


def _mock_healthy_self_reliability(monkeypatch):
    """Faz 310 — MetaStage artık self-model'i de kontrol ediyor
    (tests/test_meta_stage_self_reliability_gate.py). Bu dosya SADECE
    sideways-market gate'i izole test etmek istiyor — gerçek DB'nin
    (quantdb_test, oturum boyunca biriken kararlarla) o anki DSR/ECE
    durumuna göre kırılgan olmasın diye sağlıklı sabit değerlerle
    mock'lanıyor."""
    monkeypatch.setattr(
        "services.self_model_gatherer.get_cached_self_reliability_snapshot",
        lambda: {"inputs": {"recent_dsr": 0.99, "ece": 0.02}},
    )


def _ctx(
    adx: float | None, long_term_trend_regime: str | None,
    hurst_exponent: float | None = None, bollinger_bandwidth: float | None = None,
) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0
    ctx.market.features = {}
    if adx is not None:
        ctx.market.features["adx"] = adx
    if long_term_trend_regime is not None:
        ctx.market.features["long_term_trend_regime"] = long_term_trend_regime
    if hurst_exponent is not None:
        ctx.market.features["hurst_exponent"] = hurst_exponent
    if bollinger_bandwidth is not None:
        ctx.market.features["bollinger_bandwidth"] = bollinger_bandwidth
    return ctx


def test_low_adx_and_transition_regime_forces_wait(monkeypatch):
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=15.0, long_term_trend_regime="transition")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_low_adx_but_clear_bull_trend_does_not_force_wait(monkeypatch):
    """ADX düşük olsa bile uzun vadeli rejim NET (bull_trend) ise gate
    tetiklenmemeli — sadece İKİSİ birden belirsizken devreye girer."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=15.0, long_term_trend_regime="bull_trend")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_high_adx_with_transition_regime_does_not_force_wait(monkeypatch):
    """Uzun vadeli rejim belirsiz olsa bile ADX güçlü bir kısa vadeli
    trend gösteriyorsa (>=20) gate tetiklenmemeli."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=30.0, long_term_trend_regime="transition")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_missing_adx_does_not_force_wait(monkeypatch):
    """adx özelliği hiç yoksa (ör. yetersiz bar geçmişi) fail-closed —
    gate icat edilmiş bir değerle tetiklenmez."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=None, long_term_trend_regime="transition")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_insufficient_data_regime_does_not_force_wait(monkeypatch):
    """long_term_trend_regime='insufficient_data' (transition DEĞİL) gate'i
    tetiklememeli — bu, "rejim belirsiz/karışık" değil "henüz yeterli
    geçmiş yok" anlamına geliyor, ayrı bir durum."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=15.0, long_term_trend_regime="insufficient_data")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


# Faz 293 — Hurst ~0.5 bandı + Bollinger bandwidth sıkışması, ADX/transition
# gate'inden BAĞIMSIZ ikinci bir yol olarak eklendi. Gerçek 4949 kararlık
# veriyle doğrulandı: Hurst dead-zone TEK BAŞINA %76 oranında true (ayırt
# edici değil) — SADECE gerçekten sıkışmış bir Bollinger bandwidth'le
# (<0.03, gerçek dağılımın alt %0.5'i) birleşince anlamlı.

def test_hurst_dead_zone_and_extreme_bollinger_squeeze_forces_wait_even_with_strong_adx(monkeypatch):
    """İkinci yol: ADX güçlü olsa (gate'in eski koşulunu geçmese) bile,
    Hurst dead-zone + gerçekten aşırı sıkışmış Bollinger bandwidth AYNI
    ANDA varsa yatay piyasa olarak sayılmalı."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=30.0, long_term_trend_regime="bull_trend", hurst_exponent=0.50, bollinger_bandwidth=0.01)
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.WAIT


def test_hurst_dead_zone_alone_without_bollinger_squeeze_does_not_force_wait(monkeypatch):
    """Hurst dead-zone TEK BAŞINA (gerçek dağılımda %76 oranında true)
    gate'i tetiklememeli — ayırt edici değil, sadece gerçek bir sıkışmayla
    birlikte anlam kazanıyor."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=30.0, long_term_trend_regime="bull_trend", hurst_exponent=0.50, bollinger_bandwidth=0.15)
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_extreme_bollinger_squeeze_alone_without_hurst_dead_zone_does_not_force_wait(monkeypatch):
    """Aşırı sıkışmış Bollinger bandwidth TEK BAŞINA (Hurst net trendliyken)
    gate'i tetiklememeli — ikisi BİRLİKTE gerekiyor."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=30.0, long_term_trend_regime="bull_trend", hurst_exponent=0.85, bollinger_bandwidth=0.01)
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_moderate_bollinger_squeeze_below_typical_but_above_extreme_threshold_does_not_force_wait(monkeypatch):
    """Bollinger bandwidth eşiğin (0.03) hemen üstündeyse (ör. p10 civarı,
    0.05) — "biraz sıkışmış" ama "gerçekten aşırı" değil — Hurst dead-zone
    olsa bile gate tetiklenmemeli, eşik gerçekten sıkı tutuluyor."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(adx=30.0, long_term_trend_regime="bull_trend", hurst_exponent=0.50, bollinger_bandwidth=0.05)
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT
