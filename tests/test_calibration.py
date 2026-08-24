"""Calibration testleri."""
from services.calibration import CalibrationMetrics


def test_brier_score_perfect():
    cm = CalibrationMetrics()
    cm.record(1.0, True)
    cm.record(1.0, True)
    assert cm.brier_score() == 0.0

def test_brier_score_worst():
    cm = CalibrationMetrics()
    cm.record(1.0, False)
    cm.record(1.0, False)
    assert cm.brier_score() == 1.0

def test_ece_calculation():
    cm = CalibrationMetrics()
    for _ in range(5):
        cm.record(0.9, True)
    for _ in range(5):
        cm.record(0.1, False)
    ece = cm.expected_calibration_error(n_bins=2)
    assert ece >= 0.0

def test_reliability_diagram_all_bins():
    cm = CalibrationMetrics()
    cm.record(0.55, True)
    diagram = cm.reliability_diagram(n_bins=10)
    assert len(diagram) == 10

def test_confidence_histogram():
    cm = CalibrationMetrics()
    cm.record(0.55, True)
    cm.record(0.85, False)
    hist = cm.confidence_histogram(n_bins=10)
    assert len(hist) == 10
    total = sum(h["count"] for h in hist)
    assert total == 2
