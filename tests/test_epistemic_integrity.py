"""Epistemic Integrity Testleri — final."""
from contracts.agent import AgentOpinion, AgentDomain
from services.belief_engine import BeliefEngine

def test_partial_shared_source_detected():
    """Technical ve Quant aynı fiyat kaynağından, Order Flow farklı mikro yapıdan."""
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.9).recalculate(),
        AgentOpinion(domain=AgentDomain.QUANT, direction="LONG", confidence=0.85).recalculate(),
        AgentOpinion(domain=AgentDomain.ORDER_FLOW, direction="LONG", confidence=0.8).recalculate(),
    ]
    belief = engine.synthesize(opinions)
    assert belief.information_clusters == 2  # raw_price + orderbook
    assert 0.2 < belief.crowding_penalty < 0.5
    assert belief.strength < 1.0

def test_single_macro_outweighs_technical_crowd():
    engine = BeliefEngine()
    opinions = []
    for i in range(10):
        opinions.append(AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8).recalculate())
    opinions.append(AgentOpinion(domain=AgentDomain.MACRO, direction="SHORT", confidence=0.7).recalculate())
    belief = engine.synthesize(opinions)
    assert belief.information_clusters == 2
    assert belief.crowding_penalty > 0.6  # 1 - 1/sqrt(10) ≈ 0.684
    assert len(belief.cluster_weights) == 2

def test_same_source_contradiction_shows_disagreement():
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.9).recalculate(),
        AgentOpinion(domain=AgentDomain.QUANT, direction="SHORT", confidence=0.85).recalculate(),
    ]
    belief = engine.synthesize(opinions)
    assert belief.information_clusters == 1
    assert belief.cluster_disagreement > 0.3

def test_independent_sources_low_disagreement():
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8).recalculate(),
        AgentOpinion(domain=AgentDomain.NEWS, direction="LONG", confidence=0.8).recalculate(),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.8).recalculate(),
    ]
    belief = engine.synthesize(opinions)
    assert belief.information_clusters == 3
    assert belief.cluster_disagreement == 0.0
    assert len(belief.evidence_paths) >= 3
