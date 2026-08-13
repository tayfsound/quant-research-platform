"""Stress Testing ve Robustness (Historical Simulation) testleri — Faz 694-718 (Cognitive Core 2.0 / M8)."""
from analytics.stress_testing import apply_stress_scenario_to_notional, compute_worst_historical_drawdown


def test_finds_the_real_worst_window_in_the_series():
    # Bariz bir çöküş: index 5-7 arasında ardışık %-10 getiriler.
    returns = [0.01, 0.02, -0.01, 0.005, 0.01, -0.10, -0.10, -0.10, 0.02, 0.01]
    result = compute_worst_historical_drawdown(returns, window=3)
    assert result is not None
    assert result["worst_window_start_index"] == 5
    # (1-0.1)^3 - 1 ≈ -0.271
    assert result["worst_cumulative_return_pct"] < -0.25


def test_stable_returns_produce_a_small_worst_case():
    returns = [0.001] * 20
    result = compute_worst_historical_drawdown(returns, window=5)
    assert result["worst_cumulative_return_pct"] > 0  # hep pozitif, "en kötü" bile pozitif


def test_insufficient_data_is_fail_closed():
    returns = [0.01, 0.02, 0.03]
    assert compute_worst_historical_drawdown(returns, window=5) is None


def test_zero_or_negative_window_is_fail_closed():
    returns = [0.01] * 20
    assert compute_worst_historical_drawdown(returns, window=0) is None


def test_apply_stress_scenario_computes_real_dollar_impact():
    result = apply_stress_scenario_to_notional(worst_cumulative_return_pct=-0.15, notional=10_000.0)
    assert abs(result["dollar_impact"] - (-1500.0)) < 1e-6
    assert result["notional"] == 10_000.0
