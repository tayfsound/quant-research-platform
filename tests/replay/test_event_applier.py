from services.replay.event_applier import ReplayEventApplier


def test_event_applier():

    state = {}

    applier = ReplayEventApplier(state)

    result = applier.apply({
        "event_type": "market_update",
        "payload": {
            "BTC": 60000
        }
    })

    assert result["market"]["BTC"] == 60000
