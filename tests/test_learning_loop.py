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
