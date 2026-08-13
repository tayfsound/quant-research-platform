"""Collective Research Intelligence (Condorcet Jury Theorem) testleri — Faz 971-1000 (Cognitive Core 10.0)."""
from analytics.collective_intelligence import compute_expected_majority_accuracy


def test_matches_the_known_closed_form_for_three_agents():
    # n=3, p=0.7: P(çoğunluk doğru) = p^3 + 3*p^2*(1-p) = 0.343 + 0.441 = 0.784
    result = compute_expected_majority_accuracy([0.7, 0.7, 0.7])
    assert result is not None
    assert abs(result["expected_majority_accuracy"] - 0.784) < 1e-6


def test_skilled_agents_beat_the_best_individual():
    result = compute_expected_majority_accuracy([0.65, 0.7, 0.68, 0.72, 0.66])
    assert result["collective_beats_best_individual"] is True
    assert result["expected_majority_accuracy"] > result["best_individual_accuracy"]


def test_coin_flip_agents_gain_no_wisdom():
    result = compute_expected_majority_accuracy([0.5, 0.5, 0.5])
    assert abs(result["expected_majority_accuracy"] - 0.5) < 1e-9


def test_more_agents_converges_toward_perfect_accuracy():
    few = compute_expected_majority_accuracy([0.6] * 3)
    many = compute_expected_majority_accuracy([0.6] * 9)
    assert many["expected_majority_accuracy"] > few["expected_majority_accuracy"]


def test_single_agent_is_fail_closed():
    assert compute_expected_majority_accuracy([0.7]) is None


def test_invalid_probability_is_fail_closed():
    assert compute_expected_majority_accuracy([0.7, 1.5]) is None
    assert compute_expected_majority_accuracy([0.7, -0.1]) is None
