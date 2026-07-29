from datetime import datetime, timezone

from contracts.decision_event import DecisionEvent
from services.replay.snapshot_builder import build_snapshot
from services.replay.replay_verifier import ReplayVerifier


def test_replay_verification():

    event = DecisionEvent(
        timestamp=datetime.now(timezone.utc),
        symbol="BTCUSDT",
        final_action="BUY",
        final_size=1.0,
        confidence=0.8,
    )

    snapshot = build_snapshot(event)

    result = ReplayVerifier().verify(
        snapshot,
        event,
    )

    assert result["verified"] is True
