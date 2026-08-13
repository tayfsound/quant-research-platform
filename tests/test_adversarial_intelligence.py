"""Adversarial Intelligence testleri — Faz 941-970 (Cognitive Core 7.0)."""
from analytics.adversarial_intelligence import find_worst_performing_conditions


def _trade(win: bool, pnl: float, direction="LONG", regime="bull_trend", volatility_regime="normal") -> dict:
    return {"win": win, "pnl": pnl, "direction": direction, "regime": regime, "volatility_regime": volatility_regime}


def test_finds_the_real_worst_condition_first():
    good = [_trade(True, 5.0, regime="bull_trend") for _ in range(25)]
    bad = [_trade(False, -8.0, regime="bear_trend") for _ in range(20)] + [
        _trade(True, 5.0, regime="bear_trend") for _ in range(5)
    ]
    result = find_worst_performing_conditions(good + bad, group_by=("regime",), min_group_size=20)
    assert result[0]["condition"] == "regime=bear_trend"
    assert result[0]["win_rate"] == 0.2


def test_below_min_group_size_is_excluded():
    trades = [_trade(False, -5.0) for _ in range(5)]
    result = find_worst_performing_conditions(trades, group_by=("direction",), min_group_size=20)
    assert result == []


def test_results_are_sorted_worst_first():
    trades = (
        [_trade(True, 1.0, regime="A") for _ in range(20)]
        + [_trade(False, -1.0, regime="B") for _ in range(15)] + [_trade(True, 1.0, regime="B") for _ in range(5)]
        + [_trade(False, -1.0, regime="C") for _ in range(20)]
    )
    result = find_worst_performing_conditions(trades, group_by=("regime",), min_group_size=20, top_n=3)
    win_rates = [r["win_rate"] for r in result]
    assert win_rates == sorted(win_rates)


def test_top_n_limits_the_returned_conditions():
    trades = []
    for i, regime in enumerate(["A", "B", "C", "D"]):
        trades += [_trade(i % 2 == 0, 1.0, regime=regime) for _ in range(25)]
    result = find_worst_performing_conditions(trades, group_by=("regime",), min_group_size=20, top_n=2)
    assert len(result) == 2


def test_trades_missing_fields_are_skipped_without_crashing():
    trades = [{"win": None, "pnl": None, "direction": "LONG"}] * 25
    result = find_worst_performing_conditions(trades, group_by=("direction",), min_group_size=5)
    assert result == []
