"""Portfolio Intelligence (Effective Number of Bets) testleri — Faz 644-668 (Cognitive Core 2.0 / M6)."""
import numpy as np

from analytics.portfolio_intelligence import compute_effective_number_of_bets


def test_uncorrelated_equal_weighted_positions_approach_full_diversification():
    rng = np.random.default_rng(11)
    symbols = ["A", "B", "C", "D"]
    returns = {s: list(rng.normal(0, 1, 100)) for s in symbols}  # bağımsız
    weights = {s: 1.0 for s in symbols}
    result = compute_effective_number_of_bets(weights, returns)
    assert result is not None
    # 4 bağımsız pozisyon -> ENB 4'e yakın olmalı (mükemmel değil, örneklem gürültüsü var).
    assert result["effective_number_of_bets"] > 3.0
    assert result["diversification_ratio"] > 0.75


def test_fully_correlated_positions_collapse_to_one_effective_bet():
    rng = np.random.default_rng(3)
    base = list(rng.normal(0, 1, 100))
    returns = {"A": base, "B": base, "C": base}  # birebir aynı seri
    weights = {"A": 1.0, "B": 1.0, "C": 1.0}
    result = compute_effective_number_of_bets(weights, returns)
    assert abs(result["effective_number_of_bets"] - 1.0) < 1e-6
    assert result["position_count"] == 3


def test_fewer_than_two_symbols_is_fail_closed():
    assert compute_effective_number_of_bets({"A": 1.0}, {"A": [0.01] * 20}) is None


def test_mismatched_return_lengths_is_fail_closed():
    returns = {"A": [0.01] * 20, "B": [0.01] * 15}
    weights = {"A": 1.0, "B": 1.0}
    assert compute_effective_number_of_bets(weights, returns) is None


def test_zero_total_weight_is_fail_closed():
    returns = {"A": [0.01] * 20, "B": [0.01] * 20}
    weights = {"A": 0.0, "B": 0.0}
    assert compute_effective_number_of_bets(weights, returns) is None
