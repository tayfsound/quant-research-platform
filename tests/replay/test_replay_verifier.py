from datetime import UTC, datetime

from contracts.decision_event import DecisionEvent
from services.replay.replay_verifier import ReplayVerifier
from services.replay.snapshot_builder import build_snapshot


def test_replay_verification():

    event = DecisionEvent(
        timestamp=datetime.now(UTC),
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
