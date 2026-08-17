"""Probability Calibration ve Uncertainty (ECE) testleri — Faz 544-568 (Cognitive Core 2.0 / M4)."""
from analytics.calibration_uncertainty import (
    compute_expected_calibration_error,
    extract_predictions_from_closed_trades,
)


def test_perfectly_calibrated_predictions_score_zero_ece():
    # %80 dediğinde tam %80 doğru çıkıyor.
    predictions = [(0.8, True)] * 8 + [(0.8, False)] * 2
    result = compute_expected_calibration_error(predictions, n_bins=10)
    assert result is not None
    assert abs(result["expected_calibration_error"]) < 1e-9


def test_overconfident_predictions_have_positive_ece():
    # %90 dediğinde sadece %50 doğru çıkıyor — aşırı özgüvenli.
    predictions = [(0.9, True)] * 5 + [(0.9, False)] * 5
    result = compute_expected_calibration_error(predictions, n_bins=10)
    assert result["expected_calibration_error"] > 0.3


def test_below_min_sample_size_is_fail_closed():
    assert compute_expected_calibration_error([(0.7, True)] * 5) is None


def test_bins_report_correct_sample_sizes():
    predictions = [(0.85, True)] * 6 + [(0.15, False)] * 6
    result = compute_expected_calibration_error(predictions, n_bins=10)
    total_binned = sum(b["sample_size"] for b in result["bins"])
    assert total_binned == 12


def test_low_and_high_bins_isolate_the_same_calibration_quality_differently_from_brier():
    """ECE, iyi kalibre olan ama hep 'yanlış' tarafta emin olan bir modeli
    de doğru şekilde ölçmeli — Brier'den farklı olarak SADECE kalibrasyonu
    izole ediyor."""
    predictions = [(0.2, False)] * 8 + [(0.2, True)] * 2  # %20 dediğinde gerçekten %20 doğru
    result = compute_expected_calibration_error(predictions, n_bins=10)
    assert result["expected_calibration_error"] < 0.05


def test_extract_predictions_skips_trades_missing_confidence_or_win():
    trades = [
        {"confidence": 0.8, "outcome": {"win": True}},
        {"confidence": None, "outcome": {"win": True}},
        {"confidence": 0.6, "outcome": {}},
        {"confidence": 0.5, "outcome": {"win": False}},
    ]
    predictions = extract_predictions_from_closed_trades(trades)
    assert predictions == [(0.8, True), (0.5, False)]


def test_extract_predictions_from_empty_list_is_empty():
    assert extract_predictions_from_closed_trades([]) == []
