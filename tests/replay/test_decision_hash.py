from services.replay.decision_hash import create_decision_hash


def test_decision_hash_is_deterministic():

    data = {
        "symbol": "BTCUSDT",
        "action": "BUY",
        "size": 1.0
    }

    first = create_decision_hash(data)
    second = create_decision_hash(data)

    assert first == second
