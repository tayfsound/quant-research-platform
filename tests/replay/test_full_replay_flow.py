from datetime import datetime, timezone

from contracts.decision_event import DecisionEvent
from services.replay.snapshot_builder import build_snapshot
from services.replay.replay_session import ReplaySession
from services.replay.replay_verifier import ReplayVerifier


def test_full_replay_flow():

    event = DecisionEvent(
        timestamp=datetime.now(timezone.utc),
        symbol="BTCUSDT",
        final_action="BUY",
        final_size=2.0,
        confidence=0.9,
        market_snapshot={
            "price": 60000
        },
        belief_state={
            "trend": "bullish"
        },
    )

    snapshot = build_snapshot(event)

    session = ReplaySession(snapshot)

    state = session.run([
        {
            "event_type": "market_update",
            "payload": {
                "price": 61000
            }
        }
    ])

    verification = ReplayVerifier().verify(
        snapshot,
        event
    )

    assert state["market"]["price"] == 61000
    assert verification["verified"] is True
