from agents.source_reliability_agent import SourceReliabilityAgent

def test_annotate_adds_reliability():
    agent = SourceReliabilityAgent()
    opinions = [{"domain": "technical", "confidence": 0.8}, {"domain": "macro", "confidence": 0.6}]
    result = agent.annotate(opinions)
    assert "source_reliability" in result[0]
    assert 0 <= result[0]["source_reliability"] <= 1

def test_domain_reliability_history():
    agent = SourceReliabilityAgent()
    for _ in range(5):
        agent.annotate([{"domain": "technical", "confidence": 0.9}])
    assert agent.get_domain_reliability("technical") > 0.8
