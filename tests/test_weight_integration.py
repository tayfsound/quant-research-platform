"""Agent Weight Integration testleri."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.agent_performance import AgentPerformanceRecord
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.agent_memory import AgentMemory
from services.belief_engine import BeliefEngine
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


def test_weight_optimizer_with_memory(tmp_path):
    """Faz 242: kritik bulgu — AgentMemory() (storage_path override'sız)
    CANLI, paylaşılan agent_memory_history/agent_memory.json dosyasını
    okuyup yazıyordu (test_kelly_sizing.py/test_real_historical_backtest.py
    gibi diğer testlerin zaten izole ettiği AYNI kalıp burada eksikti).
    Gerçek üretimde artık binlerce gerçek kayıt birikmiş durumda — testin
    eklediği 20 taze kayıt, o gerçek geçmişin yanında anlamsızlaşıyor ve
    assertion artık GERÇEK üretim verisine (technical'ın yakın dönemde
    macro'dan daha kötü performans göstermesine) bağlı hale geliyor,
    testin kendi senaryosuna değil. tmp_path ile izole edildi."""
    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_history"))
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

    weight_repo = WeightRepository(storage_path=str(tmp_path / "weight_history"))
    optimizer = WeightOptimizer(memory, weight_repository=weight_repo, prior_strength=5)
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
