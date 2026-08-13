"""Cross-Asset Lead-Lag testleri — Faz 419-443 (Cognitive Core 2.0)."""
import numpy as np

from analytics.cross_asset_lead_lag import compute_lead_lag_correlation


def test_recovers_a_real_lead_lag_relationship():
    """follower, leader'ı 2 bar gecikmeyle takip ediyor — best_lag=2 olarak
    tespit edilmeli."""
    rng = np.random.default_rng(5)
    n = 60
    leader = rng.normal(0, 1, n)
    follower = np.zeros(n)
    follower[2:] = leader[:-2]  # follower[t] = leader[t-2] -> follower, leader'ı 2 bar geriden izliyor
    follower[:2] = rng.normal(0, 1, 2)

    result = compute_lead_lag_correlation(list(leader), list(follower), max_lag=5)
    assert result is not None
    assert result["best_lag"] == 2
    assert result["best_lag_correlation"] > 0.9


def test_zero_lag_when_series_move_together_synchronously():
    rng = np.random.default_rng(9)
    leader = rng.normal(0, 1, 60)
    follower = leader + rng.normal(0, 0.01, 60)  # neredeyse aynı, gecikmesiz
    result = compute_lead_lag_correlation(list(leader), list(follower), max_lag=5)
    assert result["best_lag"] == 0


def test_mismatched_lengths_are_fail_closed():
    assert compute_lead_lag_correlation([0.1] * 40, [0.1] * 35, max_lag=3) is None


def test_below_min_sample_size_is_fail_closed():
    assert compute_lead_lag_correlation([0.1] * 10, [0.1] * 10, max_lag=3) is None


def test_correlations_by_lag_covers_the_requested_range():
    rng = np.random.default_rng(3)
    leader = list(rng.normal(0, 1, 60))
    follower = list(rng.normal(0, 1, 60))
    result = compute_lead_lag_correlation(leader, follower, max_lag=3)
    assert result is not None
    assert set(result["correlations_by_lag"].keys()).issubset({-3, -2, -1, 0, 1, 2, 3})
