"""P1-8: Orchestrator facade -- tek karar yolu, cift kayit yok."""
from unittest.mock import patch
from services.orchestrator import CognitiveOrchestrator

def test_orchestrator_does_not_call_own_recorder():
    """Orchestrator, Engine.run() disinda kendi recorder'ini cagirmamalidir."""
    orch = CognitiveOrchestrator()
    with patch.object(orch.recorder, "record") as mock_record:
        orch.run_cycle(seed=42)
        mock_record.assert_not_called()

def test_orchestrator_does_not_duplicate_memory_update():
    """Orchestrator, Engine.run() disinda kendi memory'yi guncellememelidir."""
    orch = CognitiveOrchestrator()
    initial_size = len(orch.memory.memory)
    orch.run_cycle(seed=42)
    assert len(orch.memory.memory) == initial_size
