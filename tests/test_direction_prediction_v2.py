"""Direction Prediction v2 (Brier Score) testleri — Faz 519-543 (Cognitive Core 2.0 / M4)."""
from analytics.direction_prediction_v2 import compute_brier_score


def test_perfect_predictions_score_zero():
    predictions = [(1.0, True)] * 10 + [(0.0, False)] * 10
    result = compute_brier_score(predictions)
    assert result["brier_score"] == 0.0
    assert result["better_than_random"] is True


def test_worst_possible_predictions_score_one():
    predictions = [(1.0, False)] * 10 + [(0.0, True)] * 10
    result = compute_brier_score(predictions)
    assert result["brier_score"] == 1.0
    assert result["better_than_random"] is False


def test_constant_half_probability_matches_the_random_baseline():
    predictions = [(0.5, True)] * 10 + [(0.5, False)] * 10
    result = compute_brier_score(predictions)
    assert abs(result["brier_score"] - 0.25) < 1e-9
    assert result["better_than_random"] is False  # eşit, kesinlikle daha iyi değil


def test_realistic_well_calibrated_agent_beats_random():
    # %80 dediğinde %80 doğru, %20 dediğinde %20 doğru — iyi kalibre.
    predictions = [(0.8, True)] * 8 + [(0.8, False)] * 2 + [(0.2, False)] * 8 + [(0.2, True)] * 2
    result = compute_brier_score(predictions)
    assert result["better_than_random"] is True


def test_below_min_sample_size_is_fail_closed():
    assert compute_brier_score([(0.7, True)] * 5) is None
