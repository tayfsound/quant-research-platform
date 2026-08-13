"""Correlation Breakdown Detection testleri."""
import numpy as np

from analytics.correlation_breakdown import compute_correlation_breakdown


def test_detects_a_real_breakdown_from_correlated_to_decorrelated():
    rng = np.random.default_rng(7)
    baseline = rng.normal(0, 1, 100)
    # baseline: A ve B neredeyse aynı (yüksek korelasyon)
    baseline_a = list(baseline)
    baseline_b = list(baseline + rng.normal(0, 0.01, 100))
    # recent: B artık A'dan BAĞIMSIZ (korelasyon kırıldı)
    recent_a = list(rng.normal(0, 1, 50))
    recent_b = list(rng.normal(0, 1, 50))

    returns = {"A": baseline_a + recent_a, "B": baseline_b + recent_b}
    result = compute_correlation_breakdown(returns, baseline_window=100, recent_window=50, min_window_size=20)
    key = "A|B"
    assert key in result
    assert result[key]["baseline_correlation"] > 0.9
    assert result[key]["breakdown_detected"] is True


def test_stable_correlation_is_not_flagged():
    rng = np.random.default_rng(3)
    base = rng.normal(0, 1, 150)
    returns = {"A": list(base), "B": list(base + rng.normal(0, 0.01, 150))}
    result = compute_correlation_breakdown(returns, baseline_window=100, recent_window=50, min_window_size=20)
    assert result["A|B"]["breakdown_detected"] is False


def test_insufficient_data_is_excluded_fail_closed():
    returns = {"A": [0.01] * 10, "B": [0.02] * 10}
    result = compute_correlation_breakdown(returns, baseline_window=100, recent_window=50, min_window_size=20)
    assert result == {}


def test_fewer_than_two_eligible_symbols_returns_empty():
    returns = {"A": [0.01] * 200}
    result = compute_correlation_breakdown(returns, baseline_window=100, recent_window=50, min_window_size=20)
    assert result == {}


def test_multiple_symbols_report_all_pairs():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 1, 150)
    returns = {
        "A": list(base),
        "B": list(base + rng.normal(0, 0.01, 150)),
        "C": list(rng.normal(0, 1, 150)),
    }
    result = compute_correlation_breakdown(returns, baseline_window=100, recent_window=50, min_window_size=20)
    assert set(result.keys()) == {"A|B", "A|C", "B|C"}


def test_constant_returns_produce_nan_correlation_and_are_excluded():
    returns = {"A": [0.0] * 150, "B": [0.01] * 150}
    result = compute_correlation_breakdown(returns, baseline_window=100, recent_window=50, min_window_size=20)
    assert result == {}
