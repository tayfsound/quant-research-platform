"""Faz 268-sonrası — kullanıcı bulgusu: MetaStage'in güçlü-tek-ses-itirazı
kuralı, benched (effective_influence=0, kronik düşük isabet nedeniyle oyu
sıfırlanmış) bir ajanı TAMAMEN yok sayıyordu. Gerçek olay (LDOUSDT): technical
ajanı %89 güvenle, somut kanıtla (EMA'lar düşüş yönlü, fiyat VWAP'ın %80
altında) SHORT diyordu ama benched olduğu için hiç sayılmadı — sistem
sadece macro'nun %74 güvenli tek sesiyle %84.4 nihai güvenle LONG açtı.
Artık benched bir ajan da (çok daha yüksek bir barla, 0.90) WAIT'e
zorlayabiliyor — tamamen susturulmuyor."""
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


def _supportive_opinion() -> AgentOpinion:
    o = AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.74)
    o.effective_influence = 0.6
    return o


def _benched_dissenting_opinion(confidence: float) -> AgentOpinion:
    o = AgentOpinion(domain=AgentDomain.TECHNICAL, direction="SHORT", confidence=confidence)
    o.effective_influence = 0.0  # benched: performance_weight=0 -> effective_influence=0
    return o


def _ctx() -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0
    return ctx


def test_benched_opinion_with_low_confidence_does_not_force_wait():
    """Benched bir ajan gerçekten düşük güvenle konuşuyorsa (0.70 barının
    altında) kararı hâlâ etkilememeli."""
    opinions = [_supportive_opinion(), _benched_dissenting_opinion(0.60)]
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _long_belief(), opinions)

    assert result_ctx.decision.action != ActionType.WAIT


def test_benched_opinion_with_extreme_confidence_forces_wait():
    """Benched bir ajan orta-yüksek güvenle (>0.70 — gerçek LDOUSDT
    örneğindeki %89 gibi) hâlâ ters yöne işaret ediyorsa artık tamamen
    yok sayılmıyor — WAIT'e zorluyor."""
    opinions = [_supportive_opinion(), _benched_dissenting_opinion(0.89)]
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _long_belief(), opinions)

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_non_benched_opinion_still_uses_the_original_lower_threshold():
    """Regresyon kontrolü: benched OLMAYAN bir itiraz hâlâ eski eşikle
    (0.75) WAIT'e zorlamalı — yeni benched dalı eski davranışı bozmamalı."""
    dissenting = AgentOpinion(domain=AgentDomain.TECHNICAL, direction="SHORT", confidence=0.80)
    dissenting.effective_influence = 0.5  # benched DEĞİL
    opinions = [_supportive_opinion(), dissenting]
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _long_belief(), opinions)

    assert result_ctx.decision.action == ActionType.WAIT
