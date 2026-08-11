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


def test_get_summary_with_regime_only_counts_matching_regime_records(tmp_path):
    """Faz 268b — Regime-Aware Learning: aynı ajan farklı rejimlerde
    çok farklı performans gösterebilir (rapor: "TechnicalAgent trending
    piyasada harika, mean-reverting'de felaket olabilir"). get_summary()
    regime verildiğinde SADECE o rejimdeki gerçek kararları saymalı."""
    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory"))
    for _ in range(10):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.7,
            was_correct=True, market_regime="bullish_high",
        ))
    for _ in range(10):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.7,
            was_correct=False, market_regime="bearish_low",
        ))

    bullish_summary = memory.get_summary("technical", regime="bullish_high")
    bearish_summary = memory.get_summary("technical", regime="bearish_low")
    unfiltered_summary = memory.get_summary("technical")

    assert bullish_summary.total_predictions == 10
    assert bullish_summary.overall_accuracy == 1.0
    assert bearish_summary.total_predictions == 10
    assert bearish_summary.overall_accuracy == 0.0
    assert unfiltered_summary.total_predictions == 20


def test_propose_weights_with_regime_produces_a_separate_regime_tagged_snapshot(tmp_path):
    """Faz 268b — bir rejim için önerilen ağırlıklar, global öneriden
    bağımsız, kendi regime etiketiyle saklanmalı — WeightRepository.
    get_latest(regime=...) ile geri okunabilmeli."""
    import shutil

    from services.weight_repository import WeightRepository

    name = str(tmp_path / "weights_regime_test")
    try:
        memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_regime"))
        for _ in range(20):
            memory.record(AgentPerformanceRecord(
                agent_domain="technical", direction="LONG", confidence=0.8,
                was_correct=True, market_regime="bullish_high",
            ))

        repo = WeightRepository(storage_path=name)
        optimizer = WeightOptimizer(memory, weight_repository=repo)

        snapshot = optimizer.propose_weights(evaluation_window=20, regime="bullish_high")

        assert snapshot.regime == "bullish_high"
        fetched = repo.get_latest(regime="bullish_high")
        assert fetched is not None
        assert fetched.id == snapshot.id
    finally:
        shutil.rmtree(name, ignore_errors=True)
