"""Decision Recorder testleri."""
from contracts.context import CognitiveCycleContext
from services.decision_recorder import DecisionRecorder
from contracts.belief import Belief

def test_record_and_replay():
    recorder = DecisionRecorder(storage_path="test_decision_logs")
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )
    opinions = []

    event = recorder.record(ctx, opinions)
    assert event.symbol == "BTCUSDT"
    assert event.final_action != ""

    # Replay
    replayed = recorder.replay(str(event.id))
    assert replayed is not None
    assert replayed.symbol == "BTCUSDT"

    # List
    decisions = recorder.list_decisions(limit=5)
    assert len(decisions) >= 1

    # Temizlik
    import shutil
    shutil.rmtree("test_decision_logs", ignore_errors=True)
