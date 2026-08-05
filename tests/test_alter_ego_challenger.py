"""Alter Ego Challenger testleri — agent_debate.py::_run_cognitive_audit()'in
zaten aradığı ama hiç register edilmediği için hep None dönen rolü."""
from agents.critics.alter_ego import AlterEgoChallenger
from contracts.agent import AgentDomain, AgentOpinion


def _opinion(domain, direction, confidence, evidence_strength=0.5):
    return AgentOpinion(domain=domain, direction=direction, confidence=confidence, evidence_strength=evidence_strength).recalculate()


def test_near_unanimous_directional_opinions_trigger_herd_challenge():
    challenger = AlterEgoChallenger()
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.8),
        _opinion(AgentDomain.MACRO, "LONG", 0.75),
        _opinion(AgentDomain.ONCHAIN, "LONG", 0.7),
        _opinion(AgentDomain.SENTIMENT, "SHORT", 0.6),
    ]
    dummy = AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.5)
    challenges = challenger.challenge(dummy, {"opinions": [o.model_dump() for o in opinions], "rounds": []})
    assert any("herd" in c.reason.lower() for c in challenges)


def test_high_confidence_low_evidence_triggers_overconfidence_challenge():
    challenger = AlterEgoChallenger()
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.9, evidence_strength=0.2),
        _opinion(AgentDomain.MACRO, "LONG", 0.85, evidence_strength=0.25),
    ]
    dummy = AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.5)
    challenges = challenger.challenge(dummy, {"opinions": [o.model_dump() for o in opinions], "rounds": []})
    assert any("confidence" in c.reason.lower() for c in challenges)


def test_unanimous_with_zero_real_debate_triggers_confirmation_bias_challenge():
    challenger = AlterEgoChallenger()
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.6),
        _opinion(AgentDomain.MACRO, "LONG", 0.6),
        _opinion(AgentDomain.ONCHAIN, "LONG", 0.6),
    ]
    dummy = AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.5)
    # rounds boş — hiçbir gerçek itiraz üretilmemiş
    challenges = challenger.challenge(dummy, {"opinions": [o.model_dump() for o in opinions], "rounds": [{"challenges": []}]})
    assert any("bias" in c.reason.lower() for c in challenges)


def test_diverse_opinions_trigger_no_challenges():
    challenger = AlterEgoChallenger()
    opinions = [
        _opinion(AgentDomain.TECHNICAL, "LONG", 0.5, evidence_strength=0.7),
        _opinion(AgentDomain.MACRO, "SHORT", 0.5, evidence_strength=0.7),
        _opinion(AgentDomain.ONCHAIN, "WAIT", 0.3, evidence_strength=0.7),
    ]
    dummy = AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.5)
    challenges = challenger.challenge(dummy, {"opinions": [o.model_dump() for o in opinions], "rounds": [{"challenges": [{}]}]})
    assert challenges == []


def test_no_opinions_returns_no_challenges():
    challenger = AlterEgoChallenger()
    dummy = AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.5)
    assert challenger.challenge(dummy, {"opinions": [], "rounds": []}) == []
