from datetime import datetime, timezone

from contracts.replay.replay_snapshot import ReplaySnapshot
from services.replay.replay_store import ReplayStore


def test_replay_store(tmp_path):

    store = ReplayStore(
        str(tmp_path)
    )

    snapshot = ReplaySnapshot(
        snapshot_id="001",
        created_at=datetime.now(timezone.utc),
        market_state={"BTC": 60000},
    )

    store.save(snapshot)

    loaded = store.load("001")

    assert loaded["snapshot_id"] == "001"
    assert loaded["market_state"]["BTC"] == 60000
