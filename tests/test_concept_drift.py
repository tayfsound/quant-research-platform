"""Online Learning ve Concept Drift testleri — Faz 719-743 (Cognitive Core 2.0 / M9)."""
from analytics.concept_drift import compute_concept_drift


def test_detects_a_real_significant_accuracy_shift():
    baseline = [True] * 40 + [False] * 10  # %80 doğruluk
    recent = [True] * 10 + [False] * 40  # %20 doğruluk
    result = compute_concept_drift(baseline, recent)
    assert result is not None
    assert result["drift_detected"] is True
    assert result["baseline_win_rate"] == 0.8
    assert result["recent_win_rate"] == 0.2


def test_stable_accuracy_is_not_flagged():
    baseline = [True] * 30 + [False] * 20  # %60
    recent = [True] * 28 + [False] * 22  # %56 — küçük, anlamsız fark
    result = compute_concept_drift(baseline, recent)
    assert result["drift_detected"] is False


def test_below_min_sample_size_is_fail_closed():
    assert compute_concept_drift([True] * 5, [True] * 30) is None
    assert compute_concept_drift([True] * 30, [True] * 5) is None


def test_degenerate_all_same_outcome_is_handled_gracefully():
    baseline = [True] * 30
    recent = [True] * 30
    result = compute_concept_drift(baseline, recent)
    # Ya dürüstçe None (test tanımsız) ya da gerçek %100/%100 ile drift yok.
    assert result is None or (result["baseline_win_rate"] == 1.0 and result["drift_detected"] is False)
