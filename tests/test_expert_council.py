"""Expert Council testleri — stabilize API."""
from contracts.agent import AgentDomain, AgentOpinion
from services.agent_memory import AgentMemory
from services.expert_council import ExpertCouncil


class MockAgent:
    def __init__(self, domain, direction, confidence):
        self.domain = domain
        self.direction = direction
        self.confidence = confidence

    def analyze(self, context):
        return AgentOpinion(
            domain=self.domain,
            direction=self.direction,
            confidence=self.confidence,
            evidence=["mock evidence"],
        )

def test_council_deliberate():
    memory = AgentMemory()
    council = ExpertCouncil(memory)
    council.register(MockAgent(AgentDomain.TECHNICAL, "LONG", 0.8))
    council.register(MockAgent(AgentDomain.MACRO, "SHORT", 0.6))
    opinions = council.deliberate({})
    assert len(opinions) == 2

def test_council_synthesize():
    memory = AgentMemory()
    council = ExpertCouncil(memory)
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.8).recalculate(),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.6).recalculate(),
    ]
    result = council.synthesize(opinions)
    assert result.direction == "LONG"
    assert result.confidence > 0

def test_council_empty():
    memory = AgentMemory()
    council = ExpertCouncil(memory)
    result = council.synthesize([])
    assert result.direction == "WAIT"
    assert result.confidence == 0.0
