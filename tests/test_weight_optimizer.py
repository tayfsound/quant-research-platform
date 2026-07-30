"""Weight Optimizer testleri."""
from contracts.agent_performance import AgentPerformanceRecord
from services.agent_memory import AgentMemory
from services.weight_optimizer import WeightOptimizer


def test_weight_optimizer_proposes_weights():
    memory = AgentMemory()
    # Teknik ajan başarılı
    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical",
            direction="LONG",
            confidence=0.8,
            was_correct=True,
            market_regime="trend",
        ))
    # Makro ajan başarısız
    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="macro",
            direction="SHORT",
            confidence=0.6,
            was_correct=False,
            market_regime="trend",
        ))

    optimizer = WeightOptimizer(memory)
    snapshot = optimizer.propose_weights()
    assert "technical" in snapshot.weights
    assert "macro" in snapshot.weights
    # Başarılı ajanın ağırlığı, başarısızdan yüksek olmalı
    assert snapshot.weights["technical"] > snapshot.weights["macro"]
