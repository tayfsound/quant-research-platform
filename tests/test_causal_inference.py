"""Causal Cognitive Core (Granger Causality) testleri — Faz 861-900 (Cognitive Core 4.0)."""
import numpy as np

from analytics.causal_inference import compute_granger_causality


def test_detects_a_real_granger_causal_relationship():
    rng = np.random.default_rng(42)
    n = 200
    cause = rng.normal(0, 1, n)
    effect = np.zeros(n)
    for t in range(1, n):
        effect[t] = 0.8 * cause[t - 1] + rng.normal(0, 0.1)

    result = compute_granger_causality(list(cause), list(effect), max_lag=3)
    assert result is not None
    assert result["granger_causes"] is True
    assert result["best_p_value"] < 0.01


def test_independent_series_do_not_show_granger_causality():
    rng = np.random.default_rng(7)
    cause = list(rng.normal(0, 1, 150))
    effect = list(rng.normal(0, 1, 150))
    result = compute_granger_causality(cause, effect, max_lag=3)
    assert result is not None
    assert result["granger_causes"] is False


def test_mismatched_lengths_are_fail_closed():
    assert compute_granger_causality([0.1] * 50, [0.1] * 40, max_lag=2) is None


def test_below_min_sample_size_is_fail_closed():
    assert compute_granger_causality([0.1] * 10, [0.1] * 10, max_lag=2) is None


def test_constant_series_is_handled_without_crashing():
    result = compute_granger_causality([1.0] * 50, [1.0] * 50, max_lag=2)
    assert result is None
