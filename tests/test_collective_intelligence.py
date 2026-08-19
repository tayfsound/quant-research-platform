"""Collective Research Intelligence (Condorcet Jury Theorem) testleri — Faz 971-1000 (Cognitive Core 10.0)."""
from analytics.collective_intelligence import (
    compute_accuracy_confidence_interval,
    compute_expected_majority_accuracy,
)


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


def test_confidence_interval_widens_with_smaller_sample():
    """Faz 303 — n=20'de %15 nokta tahmininin gerçek belirsizliği büyük
    olmalı (dış rapor + kullanıcı bulgusu: 'son 20 örneklem' tek başına
    yanıltıcı)."""
    narrow = compute_accuracy_confidence_interval(150, 200)
    wide = compute_accuracy_confidence_interval(3, 20)
    assert (narrow["high"] - narrow["low"]) < (wide["high"] - wide["low"])


def test_confidence_interval_contains_the_point_estimate():
    ci = compute_accuracy_confidence_interval(3, 20)
    assert ci["low"] <= 3 / 20 <= ci["high"]


def test_confidence_interval_is_fail_closed_for_zero_total():
    assert compute_accuracy_confidence_interval(0, 0) is None


def test_confidence_interval_matches_known_wilson_bounds():
    # scipy binomtest(3, 20).proportion_ci(method="wilson") ile bağımsız
    # olarak doğrulandı.
    ci = compute_accuracy_confidence_interval(3, 20)
    assert abs(ci["low"] - 0.0524) < 1e-3
    assert abs(ci["high"] - 0.3604) < 1e-3
