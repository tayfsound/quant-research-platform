"""Agent Debate testleri."""
from contracts.agent import AgentChallenge, AgentDomain, AgentOpinion, AgentResponse
from services.agent_debate import AgentDebate


class MockChallenger:
    def __init__(self, domain, challenges_to_make=None):
        self.domain = domain
        self.challenges_to_make = challenges_to_make or []

    def challenge(self, opinion, context):
        result = []
        for c in self.challenges_to_make:
            target = c.get("target_domain", AgentDomain.TECHNICAL)
            if opinion.domain == target:
                result.append(AgentChallenge(
                    challenger_domain=self.domain,
                    target_domain=target,
                    reason=c.get("reason", "Disagree"),
                    confidence=c.get("confidence", 0.5),
                    evidence_strength=c.get("evidence_strength", 0.5),
                ))
        return result

class MockResponder:
    def respond(self, challenge, context):
        return AgentResponse(
            responder_domain=challenge.target_domain,
            original_challenge=challenge,
            response="Response to: " + challenge.reason,
            evidence_quality_change=-0.1,
        )

def test_debate_with_rounds():
    debate = AgentDebate(max_rounds=2)
    debate.register_challenger(AgentDomain.RISK, MockChallenger(
        AgentDomain.RISK,
        [{"target_domain": AgentDomain.TECHNICAL, "reason": "Volatility risk", "confidence": 0.7}]
    ))
    debate.register_responder(AgentDomain.TECHNICAL, MockResponder())
    opinions = [AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.85).recalculate()]
    result = debate.run_debate(opinions, {})
    assert result.final_direction == "LONG"
    assert len(result.rounds) == 2


def test_wait_votes_cannot_outvote_directional_conviction():
    """Faz 268f: kritik bulgu — düşük confidence'lı ama çoğunlukta olan
    yönlü oylar (LONG), yüksek confidence'lı ama azınlıkta olan WAIT
    oylarına yenik düşmemeli. WAIT bir yön tahmini değil, çekimser kalma
    — LONG/SHORT'u "oy" olarak yenemez, sadece nihai confidence'ı
    seyreltir."""
    debate = AgentDebate(max_rounds=0)
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.3).recalculate(),
        AgentOpinion(domain=AgentDomain.QUANT, direction="LONG", confidence=0.3).recalculate(),
        AgentOpinion(domain=AgentDomain.PATTERN, direction="LONG", confidence=0.3).recalculate(),
        AgentOpinion(domain=AgentDomain.SENTIMENT, direction="LONG", confidence=0.3).recalculate(),
        AgentOpinion(domain=AgentDomain.TIME, direction="WAIT", confidence=0.6).recalculate(),
        AgentOpinion(domain=AgentDomain.EPISTEMOLOGY, direction="WAIT", confidence=0.6).recalculate(),
    ]
    result = debate.run_debate(opinions, {})
    assert result.final_direction == "LONG"


def test_all_wait_opinions_still_resolve_to_wait():
    debate = AgentDebate(max_rounds=0)
    opinions = [
        AgentOpinion(domain=AgentDomain.TIME, direction="WAIT", confidence=0.6).recalculate(),
        AgentOpinion(domain=AgentDomain.EPISTEMOLOGY, direction="WAIT", confidence=0.6).recalculate(),
    ]
    result = debate.run_debate(opinions, {})
    assert result.final_direction == "WAIT"
