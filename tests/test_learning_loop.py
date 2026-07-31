"""Learning Loop testleri."""
from contracts.context import CognitiveCycleContext
from services.decision_recorder import DecisionRecorder
from services.learning_loop import LearningLoop


def test_process_outcome():
    # Önce bir karar kaydet
    recorder = DecisionRecorder(storage_path="test_learning_logs")
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )
    event = recorder.record(ctx, [], None)

    # Learning loop ile sonucu işle
    loop = LearningLoop()
    loop.tracker.storage_path = recorder.storage_path
    result = loop.process_outcome(str(event.id), pnl=150.0, was_correct=True)
    assert result is not None
    assert result.outcome is not None

    # İstatistikler
    stats = loop.get_stats()
    assert stats["total_predictions"] == 1

    # Temizlik
    import shutil
    shutil.rmtree("test_learning_logs", ignore_errors=True)

def test_engine_persist_and_learn_with_outcome():
    """CognitiveEngine._persist_and_learn ctx.outcome varsa learning calistirmali (P1-12)."""
    from unittest.mock import patch, MagicMock
    from contracts.outcome import TradeOutcome
    from services.cognitive_engine import CognitiveEngine

    engine = CognitiveEngine()
    ctx = MagicMock()
    ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)
    event = MagicMock()
    event.confidence = 0.8
    event.final_action = "ENTER_LONG"
    event.agent_opinions = []
    event.market_snapshot = {}

    with patch.object(engine.learning_loop, "record") as mock_record:
        with patch.object(engine.weight_optimizer, "optimize", return_value={}):
            with patch.object(engine.weight_repository, "get_latest", return_value=None):
                with patch.object(engine.weight_repository, "save"):
                    with patch("database.repositories.decision_persistor.DecisionPersistor.persist"):
                        engine._persist_and_learn(event, ctx)
                        mock_record.assert_called_once()
