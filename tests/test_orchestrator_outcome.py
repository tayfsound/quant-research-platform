"""Orchestrator outcome + single persist testleri."""
from unittest.mock import patch

from services.orchestrator import CognitiveOrchestrator


def test_orchestrator_single_persist_path():
    """Orchestrator sadece finalize() ile bir kez persist etmeli."""
    orch = CognitiveOrchestrator()
    with patch.object(orch.engine, "finalize") as mock_finalize, patch.object(orch.engine, "run") as mock_run:
        mock_ctx = mock_run.return_value
        mock_ctx.decision.proposed_direction = "NEUTRAL"
        mock_ctx.decision.final_size = 0.0
        orch.run_cycle(seed=42)
        mock_finalize.assert_called_once()
