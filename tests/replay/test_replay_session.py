from datetime import datetime, timezone

from contracts.replay.replay_snapshot import ReplaySnapshot
from services.replay.replay_session import ReplaySession


def test_replay_session():

    snapshot = ReplaySnapshot(
        snapshot_id="001",
        created_at=datetime.now(timezone.utc),
        market_state={
            "BTC": 50000
        }
    )

    session = ReplaySession(snapshot)

    result = session.run([
        {
            "event_type": "market_update",
            "payload": {
                "BTC": 60000
            }
        }
    ])

    assert result["market"]["BTC"] == 60000
