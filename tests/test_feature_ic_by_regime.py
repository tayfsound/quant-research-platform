"""analytics/feature_ic_by_regime.py — Faz 364-devam, kullanıcı isteği:
Feature IC ölçümleri rejime göre kırılmalı."""
from analytics.feature_ic_by_regime import compute_feature_ic_by_regime


def _trade(entry, exit_, feature_value, regime):
    return {
        "entry_price": entry,
        "exit_price": exit_,
        "market_regime": regime,
        "agent_contributions": [
            {"domain": "technical", "feature_contributions": {"my_feature": feature_value}},
        ],
    }


def test_groups_trades_by_regime_before_computing_ic():
    trades = []
    for i in range(25):
        trades.append(_trade(100, 100 + i, i * 0.1, "bullish_low"))
    for i in range(25):
        trades.append(_trade(100, 100 - i, i * 0.1, "bearish_low"))

    result = compute_feature_ic_by_regime(trades, min_sample_size=20)

    assert set(result.keys()) == {"bullish_low", "bearish_low"}
    assert result["bullish_low"]["my_feature"]["ic"] > 0.9
    assert result["bearish_low"]["my_feature"]["ic"] < -0.9


def test_trades_without_regime_are_excluded():
    trades = [_trade(100, 110, 0.5, None) for _ in range(25)]
    result = compute_feature_ic_by_regime(trades, min_sample_size=20)
    assert result == {}


def test_each_regime_applies_its_own_min_sample_size():
    trades = [_trade(100, 100 + i, i * 0.1, "bullish_low") for i in range(5)]
    result = compute_feature_ic_by_regime(trades, min_sample_size=20)
    assert result["bullish_low"] == {}


def test_empty_input_is_fail_closed():
    assert compute_feature_ic_by_regime([]) == {}
