"""Faz 407 — agent_combination_reliability_gatherer.py'nin her çifte
(domains) geçmiş snapshot'lardan win_rate_stability eklediğini
doğruluyor. historical_analog_gatherer'daki AYNI desen/disiplin."""
from services.agent_combination_reliability_gatherer import _attach_win_rate_stability, _pair_key


def _pair(domains, win_rate):
    return {"domains": domains, "win_rate": win_rate}


def test_attaches_none_when_no_past_snapshots_exist():
    pairs = [_pair(["macro", "technical"], 0.75)]
    _attach_win_rate_stability(pairs, past_snapshots=[])
    assert pairs[0]["win_rate_stability"] is None


def test_attaches_real_stability_from_matching_past_snapshots():
    pairs = [_pair(["macro", "technical"], 0.80)]
    past_snapshots = [
        {"result": {"pairs": [_pair(["macro", "technical"], 0.60)]}},
        {"result": {"pairs": [_pair(["macro", "technical"], 0.70)]}},
    ]
    _attach_win_rate_stability(pairs, past_snapshots)

    stability = pairs[0]["win_rate_stability"]
    assert stability["n"] == 3
    assert abs(stability["mean"] - 0.70) < 1e-9


def test_pair_key_is_order_independent():
    assert _pair_key(_pair(["technical", "macro"], 0.5)) == _pair_key(_pair(["macro", "technical"], 0.9))
