"""P1-8: Orchestrator facade -- tek karar yolu, cift kayit yok."""
from unittest.mock import patch
from services.orchestrator import CognitiveOrchestrator

def test_orchestrator_does_not_call_own_recorder():
    """Orchestrator, Engine.run() disinda kendi recorder'ini cagirmamalidir."""
    orch = CognitiveOrchestrator()
    with patch.object(orch.recorder, "record") as mock_record:
        orch.run_cycle(seed=42)
        mock_record.assert_not_called()

def test_orchestrator_calls_finalize_once():
    """Orchestrator, engine.run(persist=False) sonrasi finalize() cagirmali."""
    from unittest.mock import patch
    orch = CognitiveOrchestrator()
    with patch.object(orch.engine, "finalize") as mock_finalize:
        with patch.object(orch.engine, "run") as mock_run:
            mock_ctx = mock_run.return_value
            mock_ctx.decision.proposed_direction = "NEUTRAL"
            mock_ctx.decision.final_size = 0.0
            orch.run_cycle(seed=42)
            mock_finalize.assert_called_once()
