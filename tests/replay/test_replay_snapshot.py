from datetime import datetime, timezone

from contracts.replay.replay_snapshot import ReplaySnapshot


def test_snapshot_creation():

    snapshot = ReplaySnapshot(
        snapshot_id="test-001",
        created_at=datetime.now(timezone.utc),
        market_state={"BTC": 60000},
        beliefs={"trend": "bullish"}
    )

    assert snapshot.snapshot_id == "test-001"
    assert snapshot.market_state["BTC"] == 60000
