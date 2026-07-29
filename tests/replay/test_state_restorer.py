from services.replay.state_restorer import ReplayStateRestorer


def test_state_restore():

    data = {
        "snapshot_id": "001",
        "created_at": "2026-01-01T00:00:00",
        "market_state": {
            "BTC": 60000
        },
        "belief_state": {
            "trend": "bullish"
        }
    }

    snapshot = ReplayStateRestorer().restore(data)

    assert snapshot.snapshot_id == "001"
    assert snapshot.market_state["BTC"] == 60000
    assert snapshot.belief_state["trend"] == "bullish"
