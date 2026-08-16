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


def _ctx(adx: float | None, long_term_trend_regime: str | None) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0
    ctx.market.features = {}
    if adx is not None:
        ctx.market.features["adx"] = adx
    if long_term_trend_regime is not None:
        ctx.market.features["long_term_trend_regime"] = long_term_trend_regime
    return ctx


def test_low_adx_and_transition_regime_forces_wait():
    ctx = _ctx(adx=15.0, long_term_trend_regime="transition")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_low_adx_but_clear_bull_trend_does_not_force_wait():
    """ADX düşük olsa bile uzun vadeli rejim NET (bull_trend) ise gate
    tetiklenmemeli — sadece İKİSİ birden belirsizken devreye girer."""
    ctx = _ctx(adx=15.0, long_term_trend_regime="bull_trend")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_high_adx_with_transition_regime_does_not_force_wait():
    """Uzun vadeli rejim belirsiz olsa bile ADX güçlü bir kısa vadeli
    trend gösteriyorsa (>=20) gate tetiklenmemeli."""
    ctx = _ctx(adx=30.0, long_term_trend_regime="transition")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_missing_adx_does_not_force_wait():
    """adx özelliği hiç yoksa (ör. yetersiz bar geçmişi) fail-closed —
    gate icat edilmiş bir değerle tetiklenmez."""
    ctx = _ctx(adx=None, long_term_trend_regime="transition")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT


def test_insufficient_data_regime_does_not_force_wait():
    """long_term_trend_regime='insufficient_data' (transition DEĞİL) gate'i
    tetiklememeli — bu, "rejim belirsiz/karışık" değil "henüz yeterli
    geçmiş yok" anlamına geliyor, ayrı bir durum."""
    ctx = _ctx(adx=15.0, long_term_trend_regime="insufficient_data")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _long_belief(), _supportive_opinions())

    assert result_ctx.decision.action != ActionType.WAIT
