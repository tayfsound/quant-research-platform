"""Scientific Self-Correction (Hypothesis Retest) testleri — Faz 1061-1100 (Cognitive Core 8.0-9.0)."""
from analytics.scientific_self_correction import compute_hypothesis_retest


def test_stable_hypothesis_remains_valid():
    result = compute_hypothesis_retest(original_wins=130, original_n=200, recent_wins=64, recent_n=100)
    assert result is not None
    assert result["significant_change"] is False
    assert result["hypothesis_still_valid"] is True


def test_collapsed_edge_is_flagged_as_no_longer_valid():
    # Orijinal %65, güncel %20 — gerçek bir edge kaybı.
    result = compute_hypothesis_retest(original_wins=130, original_n=200, recent_wins=20, recent_n=100)
    assert result["significant_change"] is True
    assert result["hypothesis_still_valid"] is False


def test_strengthened_edge_remains_valid_even_if_significant():
    # Orijinal %50, güncel %85 — edge kaybolmadı, güçlendi.
    result = compute_hypothesis_retest(original_wins=100, original_n=200, recent_wins=85, recent_n=100)
    assert result["hypothesis_still_valid"] is True


def test_below_min_sample_size_is_fail_closed():
    assert compute_hypothesis_retest(5, 10, 50, 100) is None
    assert compute_hypothesis_retest(50, 100, 5, 10) is None


def test_degenerate_zero_variance_case_is_fail_closed():
    # Her iki grupta da %0 kazanma — p_pooled=0, standart hata sıfır.
    result = compute_hypothesis_retest(original_wins=0, original_n=50, recent_wins=0, recent_n=50)
    assert result is None
