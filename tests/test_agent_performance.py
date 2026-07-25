"""Agent Performance testleri."""
from contracts.agent_performance import AgentPerformanceRecord
from services.agent_memory import AgentMemory

def test_agent_memory_records_and_summarizes():
    memory = AgentMemory()
    memory.record(AgentPerformanceRecord(
        agent_domain="technical",
        direction="LONG",
        confidence=0.8,
        was_correct=True,
        market_regime="trend",
    ))
    memory.record(AgentPerformanceRecord(
        agent_domain="technical",
        direction="SHORT",
        confidence=0.6,
        was_correct=False,
        market_regime="range",
    ))
    summary = memory.get_summary("technical")
    assert summary.total_predictions == 2
    assert summary.overall_accuracy == 0.5
    assert summary.by_regime["trend"] == 1.0
    assert summary.by_regime["range"] == 0.0

def test_contextual_confidence():
    memory = AgentMemory()
    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="macro",
            direction="LONG",
            confidence=0.7,
            was_correct=True,
            market_regime="trend",
        ))
    conf = memory.get_contextual_confidence("macro", market_regime="trend")
    assert conf > 0.5

def test_empty_agent_returns_neutral():
    memory = AgentMemory()
    conf = memory.get_contextual_confidence("unknown")
    assert conf == 0.5
