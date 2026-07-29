"""Decision Recorder compatibility tests."""

from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor
from services.decision_recorder import DecisionRecorder
from contracts.context import CognitiveCycleContext


def test_record_and_replay():
    recorder = DecisionRecorder()

    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )

    event = recorder.record(ctx, [])

    assert event.symbol == "BTCUSDT"
    assert event.final_action != ""

    session = get_session()

    try:
        persistor = DecisionPersistor(session)

        persistor.persist(event)

        replayed = recorder.replay(str(event.id))

        assert replayed is not None
        assert replayed.symbol == "BTCUSDT"

        decisions = recorder.list_decisions(limit=5)

        assert len(decisions) >= 1

    finally:
        session.close()
