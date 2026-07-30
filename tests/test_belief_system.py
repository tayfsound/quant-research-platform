"""Belief System V3 testleri."""
from contracts.agent import AgentDomain, AgentOpinion
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
