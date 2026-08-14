"""Faz 268-sonrası — kullanıcı bulgusu: eski implementasyon "reliability"i
son 10 kararın ORTALAMA CONFIDENCE'i olarak hesaplıyordu, ajanın GERÇEKTEN
doğru tahmin edip etmediğine hiç bakmıyordu. Artık services/agent_memory.py
::AgentMemory'nin gerçek (was_correct alanlı) kayıtlarından, gerçek isabet
oranı üzerinden hesaplanıyor."""
from datetime import datetime, timedelta

from agents.source_reliability_agent import SourceReliabilityAgent
from contracts.agent_performance import AgentPerformanceRecord
from services.agent_memory import AgentMemory


def _seed(memory: AgentMemory, domain: str, n: int, was_correct: bool, confidence: float = 0.9) -> None:
    for _ in range(n):
        memory.record(AgentPerformanceRecord(
            agent_domain=domain, direction="LONG", confidence=confidence, was_correct=was_correct,
        ))


def test_reliability_reflects_real_accuracy_not_confidence(tmp_path):
    """Kritik ayrım: ajan HEP yüksek confidence (0.95) bildiriyor ama
    GERÇEKTE hep yanlış çıkıyor — reliability düşük olmalı, yüksek değil."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "technical", 15, was_correct=False, confidence=0.95)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "technical", "confidence": 0.95}])

    assert result[0]["source_reliability"] < 0.35
    assert result[0]["benched"] is True


def test_reliability_reflects_genuinely_correct_track_record(tmp_path):
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "macro", 15, was_correct=True, confidence=0.5)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "macro", "confidence": 0.5}])

    assert result[0]["source_reliability"] > 0.8
    assert result[0]["benched"] is False


def test_insufficient_real_samples_is_neutral_not_benched(tmp_path):
    """Fail-closed: yeterli gerçek kanıt (MIN_SAMPLES) yoksa nötr (tam
    ağırlık) — "kanıtlanana kadar güven", eksik veriyle cezalandırma değil."""
    memory = AgentMemory(storage_path=str(tmp_path))
    _seed(memory, "onchain", 3, was_correct=False)

    agent = SourceReliabilityAgent(memory=memory)
    result = agent.annotate([{"domain": "onchain", "confidence": 0.5}])

    assert result[0]["source_reliability"] == 0.5
    assert result[0]["benched"] is False


def test_state_persists_across_fresh_instances_not_reset_every_call(tmp_path):
    """Kritik bulgu: eski implementasyon in-process bir dict'te tutuyordu
    ve her yeni CognitiveOrchestrator (dolayısıyla her run_trading_cycle_
    task çağrısı, 120 saniyede bir) ile sıfırlanıyordu. Artık AgentMemory
    diskten okunuyor — YENİ bir SourceReliabilityAgent örneği bile aynı
    gerçek geçmişi görmeli."""
    memory_path = str(tmp_path)
    seed_memory = AgentMemory(storage_path=memory_path)
    _seed(seed_memory, "quant", 15, was_correct=False, confidence=0.9)

    # Tamamen YENİ bir örnek — hiçbir in-process state paylaşmıyor.
    fresh_agent = SourceReliabilityAgent(memory=AgentMemory(storage_path=memory_path))
    result = fresh_agent.annotate([{"domain": "quant", "confidence": 0.9}])

    assert result[0]["benched"] is True


def test_legacy_records_before_cutoff_do_not_count(tmp_path, monkeypatch):
    """Kullanıcı isteği: "başlangıç olarak her ajanın kararda eşit
    ağırlığı olsun." reliability_legacy_cutoff_at set edildiğinde, o
    tarihten ÖNCEKİ kayıtlar (eski/bozuk mekanizmanın dönemi) yeni hesaba
    hiç girmemeli."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    memory = AgentMemory(storage_path=str(tmp_path))
    old_record = AgentPerformanceRecord(
        agent_domain="pattern", direction="LONG", confidence=0.9, was_correct=False,
        timestamp=datetime.now() - timedelta(days=2),
    )
    memory._records.setdefault("pattern", []).append(old_record)
    memory._save()
    _seed(memory, "pattern", 12, was_correct=True, confidence=0.6)

    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    with SessionFactory.get_session() as session:
        original = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
        AppSettingsRepository(session).set("reliability_legacy_cutoff_at", cutoff, updated_by="test")
    try:
        agent = SourceReliabilityAgent(memory=memory)
        result = agent.annotate([{"domain": "pattern", "confidence": 0.6}])
        assert result[0]["benched"] is False
        assert result[0]["source_reliability"] > 0.8
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("reliability_legacy_cutoff_at", original, updated_by="test")
