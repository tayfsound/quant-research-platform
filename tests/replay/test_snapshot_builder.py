from datetime import UTC, datetime

from contracts.decision_event import DecisionEvent
from services.replay.snapshot_builder import build_snapshot


def test_snapshot_builder():

    event = DecisionEvent(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        final_action="BUY",
        final_size=1.0,
        confidence=0.8,
    )

    snapshot = build_snapshot(event)

    assert snapshot.decision_event_id == str(event.id)
    assert snapshot.decision_hash
