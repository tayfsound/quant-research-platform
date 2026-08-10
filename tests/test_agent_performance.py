"""Agent Performance testleri."""
from contracts.agent_performance import AgentPerformanceRecord
from services.agent_memory import AgentMemory


def test_agent_memory_records_and_summarizes(tmp_path):
    memory = AgentMemory(
        storage_path=str(tmp_path / "memory")
    )

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


def test_get_summary_window_only_counts_the_most_recent_records(tmp_path):
    """Faz 263: kritik bulgu — WeightOptimizer window'suz çağırdığı için
    ağırlıklar hep tüm-zamanlar ortalamasına göre belirleniyordu, bir
    ajanın YAKIN ZAMANDA çökmüş olması hiç yansımıyordu (gerçek bulgu:
    technical_agent tüm-zamanlar %76.7 ama son 20 tahmininin %15'i
    doğru). window verilince sadece o kadar en yeni kayıt sayılmalı."""
    memory = AgentMemory(storage_path=str(tmp_path / "memory"))

    # Eski, iyi bir dönem: 8 doğru, 2 yanlış.
    for _ in range(8):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.8, was_correct=True,
        ))
    for _ in range(2):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="LONG", confidence=0.8, was_correct=False,
        ))
    # Yakın zamanda çöküş: son 5 tahminin sadece 1'i doğru.
    for _ in range(4):
        memory.record(AgentPerformanceRecord(
            agent_domain="technical", direction="SHORT", confidence=0.6, was_correct=False,
        ))
    memory.record(AgentPerformanceRecord(
        agent_domain="technical", direction="SHORT", confidence=0.6, was_correct=True,
    ))

    all_time = memory.get_summary("technical")
    assert all_time.overall_accuracy == 0.6  # (8+1)/15

    windowed = memory.get_summary("technical", window=5)
    assert windowed.total_predictions == 5
    assert windowed.overall_accuracy == 0.2  # sadece son 5 kayıt: 1/5


def test_contextual_confidence(tmp_path):
    memory = AgentMemory(
        storage_path=str(tmp_path / "memory")
    )

    for _ in range(20):
        memory.record(AgentPerformanceRecord(
            agent_domain="macro",
            direction="LONG",
            confidence=0.7,
            was_correct=True,
            market_regime="trend",
        ))

    conf = memory.get_contextual_confidence(
        "macro",
        market_regime="trend",
    )

    assert conf > 0.5


def test_empty_agent_returns_neutral(tmp_path):
    memory = AgentMemory(
        storage_path=str(tmp_path / "memory")
    )

    conf = memory.get_contextual_confidence("unknown")

    assert conf == 0.5


def test_wait_only_agent_summary_has_zero_predictions_not_fake_accuracy(tmp_path):
    """Faz 253: kritik bulgu — canlıda doğrulandı. time/epistemology
    ajanları HİÇ yönlü tahmin yapmadı (her zaman WAIT, tasarım gereği —
    bkz. agents/time_agent.py, agents/epistemology_agent.py), ama
    get_summary() bu WAIT kayıtlarını da doğruluk hesabına katıp
    WeightOptimizer'a "%82.5 doğru" gibi sahte bir beceri sinyali
    veriyordu — kullanıcı bunu fark etmeden bir ağırlık onayı olarak
    kabul etti. Artık SADECE gerçekten yönlü (LONG/SHORT) kayıtlar
    sayılıyor; sadece WAIT kaydı olan bir ajan total_predictions=0
    (nötr) döndürmeli, sahte bir doğruluk değil."""
    memory = AgentMemory(storage_path=str(tmp_path / "memory"))

    for _ in range(10):
        memory.record(AgentPerformanceRecord(
            agent_domain="time",
            direction="WAIT",
            confidence=0.3,
            was_correct=True,  # eski (Faz 245 öncesi) davranışta bile olsa
        ))

    summary = memory.get_summary("time")
    assert summary.total_predictions == 0
    assert summary.overall_accuracy == 0.0


def test_get_summary_ignores_wait_records_mixed_with_directional_ones(tmp_path):
    memory = AgentMemory(storage_path=str(tmp_path / "memory"))

    memory.record(AgentPerformanceRecord(
        agent_domain="onchain", direction="LONG", confidence=0.6, was_correct=True,
    ))
    memory.record(AgentPerformanceRecord(
        agent_domain="onchain", direction="WAIT", confidence=0.2, was_correct=True,
    ))
    memory.record(AgentPerformanceRecord(
        agent_domain="onchain", direction="WAIT", confidence=0.2, was_correct=False,
    ))

    summary = memory.get_summary("onchain")
    assert summary.total_predictions == 1
    assert summary.overall_accuracy == 1.0
