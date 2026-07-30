"""Agent Weight Integration testleri."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.agent_performance import AgentPerformanceRecord
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.agent_memory import AgentMemory
from services.belief_engine import BeliefEngine
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


def test_weight_optimizer_with_memory():
    memory = AgentMemory()
    # Technical: 18/20 doğru
    for _ in range(18):
        memory.record(AgentPerformanceRecord(agent_domain="technical", direction="LONG", confidence=0.8, was_correct=True))
    for _ in range(2):
        memory.record(AgentPerformanceRecord(agent_domain="technical", direction="LONG", confidence=0.8, was_correct=False))

    # Macro: 8/20 doğru
    for _ in range(8):
        memory.record(AgentPerformanceRecord(agent_domain="macro", direction="LONG", confidence=0.7, was_correct=True))
    for _ in range(12):
        memory.record(AgentPerformanceRecord(agent_domain="macro", direction="LONG", confidence=0.7, was_correct=False))

    optimizer = WeightOptimizer(memory, prior_strength=5)
    snapshot = optimizer.propose_weights(evaluation_window=20)

    assert snapshot.weights["technical"] > snapshot.weights["macro"]
    assert snapshot.snapshot_hash != ""

def test_snapshot_persistence():
    repo = WeightRepository(storage_path="test_weights")
    snapshot = AgentWeightSnapshot(
        weights={"technical": 1.2, "macro": 0.7},
        reason="test",
    ).finalize()
    repo.save(snapshot)
    loaded = repo.get_latest()
    assert loaded is not None
    assert loaded.weights["technical"] == 1.2
    import shutil
    shutil.rmtree("test_weights", ignore_errors=True)

def test_belief_engine_applies_weights():
    engine = BeliefEngine()
    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.9).recalculate(),
        AgentOpinion(domain=AgentDomain.MACRO, direction="SHORT", confidence=0.7).recalculate(),
    ]

    # Eşit ağırlıkla
    belief_equal = engine.apply_weights(opinions, None)

    # Technical'e 2x ağırlık ver
    snapshot = AgentWeightSnapshot(weights={"technical": 2.0, "macro": 1.0}).finalize()
    belief_weighted = engine.apply_weights(opinions, snapshot)

    # Ağırlıklı versiyonda LONG'a daha fazla güven olmalı
    assert belief_weighted.strength >= belief_equal.strength
