"""MAE/MFE Bilimsel Motoru testleri — Faz 469-493 (Cognitive Core 2.0)."""
import numpy as np

from analytics.mae_mfe_scientific import bootstrap_quantile_ci


def test_point_estimate_matches_the_real_sample_quantile():
    values = list(np.linspace(0.01, 0.10, 50))
    result = bootstrap_quantile_ci(values, quantile=0.9, n_bootstrap=200)
    assert result is not None
    assert abs(result["point_estimate"] - float(np.quantile(values, 0.9))) < 1e-9


def test_confidence_interval_contains_the_point_estimate():
    rng = np.random.default_rng(1)
    values = list(rng.normal(0.02, 0.005, 60))
    result = bootstrap_quantile_ci(values, quantile=0.9, n_bootstrap=500)
    assert result["ci_lower"] <= result["point_estimate"] <= result["ci_upper"]


def test_below_min_sample_size_is_fail_closed():
    assert bootstrap_quantile_ci([0.01, 0.02, 0.03], quantile=0.9) is None


def test_larger_sample_produces_a_tighter_confidence_interval():
    rng = np.random.default_rng(2)
    small_sample = list(rng.normal(0.02, 0.01, 15))
    large_sample = list(rng.normal(0.02, 0.01, 500))
    small_result = bootstrap_quantile_ci(small_sample, quantile=0.9, n_bootstrap=500)
    large_result = bootstrap_quantile_ci(large_sample, quantile=0.9, n_bootstrap=500)
    small_width = small_result["ci_upper"] - small_result["ci_lower"]
    large_width = large_result["ci_upper"] - large_result["ci_lower"]
    assert large_width < small_width


def test_same_seed_produces_reproducible_results():
    values = list(np.linspace(0.01, 0.10, 40))
    result_a = bootstrap_quantile_ci(values, quantile=0.9, n_bootstrap=200, random_seed=7)
    result_b = bootstrap_quantile_ci(values, quantile=0.9, n_bootstrap=200, random_seed=7)
    assert result_a == result_b
