"""Belief System V3 testleri."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.belief_engine import BeliefEngine


def test_independent_clusters():
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8).recalculate(),
        AgentOpinion(domain=AgentDomain.NEWS, direction="LONG", confidence=0.7).recalculate(),
        AgentOpinion(domain=AgentDomain.ONCHAIN, direction="LONG", confidence=0.6).recalculate(),
    ]
    belief = engine.synthesize(opinions)
    assert belief.direction == "LONG"
    assert belief.information_clusters >= 2

def test_dependent_sources_low_strength():
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.9).recalculate(),
        AgentOpinion(domain=AgentDomain.QUANT, direction="LONG", confidence=0.85).recalculate(),
    ]
    belief = engine.synthesize(opinions)
    assert belief.strength < 0.9

def test_entropy_calculation():
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.5).recalculate(),
        AgentOpinion(domain=AgentDomain.MACRO, direction="SHORT", confidence=0.5).recalculate(),
    ]
    belief = engine.synthesize(opinions)
    assert belief.entropy > 0


def test_apply_weights_does_not_resurrect_a_benched_agents_vote():
    """Gerçek bulgu: CouncilOrchestrator.deliberate() güvenilirliği düşük
    ajanları performance_weight=0 yaparak "bench" ediyor (oyu geçersiz
    kılıyor). apply_weights() bunu bir weight snapshot'ıyla EZİYORDU —
    bench'lenmiş bir ajan snapshot'ta yüksek ağırlığa sahipse oyu tam güçle
    geri dönüyordu. Doğru davranış: iki sinyal çarpılmalı, snapshot bench'i
    asla geri getirmemeli."""
    engine = BeliefEngine()
    benched_wait = AgentOpinion(
        domain=AgentDomain.MACRO, direction="WAIT", confidence=0.9,
        performance_weight=0.0,  # bench edilmiş
    ).recalculate()
    healthy_long = AgentOpinion(
        domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.7,
    ).recalculate()

    # Snapshot, bench'lenmiş ajana da yüksek ağırlık veriyor olsun (gerçek
    # üretimdeki durum: WeightRepository snapshot'ı reliability annotator'dan
    # habersiz).
    snapshot = AgentWeightSnapshot(weights={"macro": 0.99, "technical": 0.96}).finalize()

    belief = engine.apply_weights([benched_wait, healthy_long], snapshot)

    assert belief.direction == "LONG"
