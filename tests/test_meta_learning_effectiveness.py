"""Meta-Learning ve Self-Improving Intelligence testleri — Faz 744-768 (Cognitive Core 2.0 / M10)."""
from analytics.meta_learning_effectiveness import compute_meta_learning_trend


def test_detects_a_real_improving_trend():
    # Her tur giderek daha iyi sharpe_improvement üretiyor.
    improvements = [0.01, 0.02, 0.03, 0.05, 0.06, 0.08, 0.09, 0.11, 0.12, 0.14]
    result = compute_meta_learning_trend(improvements)
    assert result is not None
    assert result["trend"] == "improving"
    assert result["spearman_correlation"] > 0.9


def test_detects_a_real_degrading_trend():
    improvements = [0.14, 0.12, 0.11, 0.09, 0.08, 0.06, 0.05, 0.03, 0.02, 0.01]
    result = compute_meta_learning_trend(improvements)
    assert result["trend"] == "degrading"
    assert result["spearman_correlation"] < -0.9


def test_random_noise_shows_no_significant_trend():
    # Sıra ile hiç ilişkisi olmayan bir desen (alternan yüksek/düşük).
    improvements = [0.05, -0.03, 0.04, -0.02, 0.06, -0.05, 0.03, -0.04, 0.05, -0.03]
    result = compute_meta_learning_trend(improvements)
    assert result["trend"] == "no_significant_trend"


def test_below_min_rounds_is_fail_closed():
    assert compute_meta_learning_trend([0.01, 0.02, 0.03]) is None


def test_constant_series_is_handled_without_crashing():
    result = compute_meta_learning_trend([0.05] * 10)
    assert result is None or result["trend"] == "no_significant_trend"
