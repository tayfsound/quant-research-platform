"""Decision Recorder compatibility tests."""
from datetime import UTC, datetime, timedelta

from contracts.context import CognitiveCycleContext
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor
from services.decision_recorder import DecisionRecorder


def test_record_computes_real_decision_latency_from_last_bar_timestamp():
    """Faz 268-sonrası — kritik bulgu: decision_latency_ms hiç
    doldurulmuyordu (her zaman 0.0 varsayılan). Artık ctx.market.
    raw_snapshot'taki GERÇEK last_bar_timestamp ile ctx.timestamp
    arasındaki farktan hesaplanıyor."""
    recorder = DecisionRecorder()
    now = datetime.now(UTC)
    last_bar = now - timedelta(seconds=45)

    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "raw_snapshot": {"last_bar_timestamp": last_bar.isoformat()}},
        decision={"proposed_size": 0.5},
    )
    ctx.timestamp = now

    event = recorder.record(ctx, [])
    assert 44000 <= event.decision_latency_ms <= 46000


def test_record_defaults_decision_latency_to_zero_without_last_bar_timestamp():
    recorder = DecisionRecorder()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )
    event = recorder.record(ctx, [])
    assert event.decision_latency_ms == 0.0


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
