"""RecordingStage: recorder + belief store side effects."""
from unittest.mock import MagicMock, patch


def test_recording_stage_calls_recorder_and_belief_store():
    from contracts.belief import Belief
    from contracts.context import CognitiveCycleContext
    from engines.cognitive_pipeline import RecordingStage

    stage = RecordingStage()
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    belief = Belief(direction="LONG", strength=0.8, uncertainty=0.2)

    with patch.object(stage.recorder, "record") as mock_record:
        with patch("services.memory_service.MemoryService.store_belief") as mock_store:
            mock_record.return_value = MagicMock()
            event = stage.execute(ctx, belief, [])
            mock_record.assert_called_once()
            mock_store.assert_called_once_with(belief)
            assert event is not None
