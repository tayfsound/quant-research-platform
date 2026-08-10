"""Faz 268i/268j — kritik bulgu, kullanıcı kararıyla acil düzeltildi:
CognitiveEngine.finalize()'ın memory_engine.execute(ctx) çağrısı, HER
cycle'da (gerçek bir pozisyon kapanışı değil, aynı cycle içinde n-bar
ileri hesaplanan sahte bir ForwardOutcome ile) episodic/pgvector hafızaya
yazıyordu. services/decision_context_builder.py (MemoryStage üzerinden,
council oy vermeden ÖNCE HER cycle'da çalışıyor) bu hafızadan "benzer
durumda ne oldu" diye bir MemoryInsight üretip canlı karar motoruna
enjekte ediyordu — yani sahte n-bar sonuçları gerçek kararları
etkiliyordu (Faz 250'nin AgentMemory/WeightOptimizer için kapattığı AYNI
sızıntının bir eşi).

Bu dosya önceden ("Gap #8") tam tersini doğruluyordu — bu yazmanın
gerçekleştiğini kanıtlıyordu. Artık TERSİNİ doğruluyor: finalize()
episodic hafızaya YAZMIYOR (gerçek kapanışlarla beslenene kadar, bkz.
services/cognitive_engine.py::finalize()'ın güncel docstring'i)."""
from uuid import uuid4

from sqlalchemy import text

from database.session_factory import SessionFactory
from services.orchestrator import CognitiveOrchestrator


def test_live_cycles_do_not_write_episodes_from_fake_forward_outcome():
    symbol = f"MEMWIRE{uuid4().hex[:8]}"
    orch = CognitiveOrchestrator()
    orch.run_cycle(seed=101, symbol=symbol)
    orch.run_cycle(seed=102, symbol=symbol)

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("SELECT id FROM episodes WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).mappings().all()

    assert len(rows) == 0
