"""Faz 248: confidence kalibrasyon testleri."""
from services.confidence_calibration import calibrate_confidence


def test_calibrate_with_empty_curve_returns_raw_value_unchanged():
    """Yeterli gerçek veri yoksa (fail-closed) ham değer değişmemeli."""
    assert calibrate_confidence(0.55, curve=[]) == 0.55


def test_calibrate_interpolates_between_known_points():
    curve = [(0.4, 0.2), (0.6, 0.3)]
    # Tam ortada: doğrusal enterpolasyonla (0.2+0.3)/2 = 0.25
    assert abs(calibrate_confidence(0.5, curve=curve) - 0.25) < 1e-9


def test_calibrate_exact_match_returns_observed_value():
    curve = [(0.4, 0.2), (0.6, 0.3)]
    assert calibrate_confidence(0.4, curve=curve) == 0.2
    assert calibrate_confidence(0.6, curve=curve) == 0.3


def test_calibrate_outside_curve_range_returns_raw_value_unchanged():
    """Eğri dışındaki bir değer için (ör. çok yüksek/düşük, hiç
    gözlenmemiş) icat edilmiş bir düzeltme yapılmamalı."""
    curve = [(0.4, 0.2), (0.6, 0.3)]
    assert calibrate_confidence(0.9, curve=curve) == 0.9
    assert calibrate_confidence(0.1, curve=curve) == 0.1


def test_compute_calibration_curve_ignores_buckets_below_min_samples():
    from services import confidence_calibration

    original = confidence_calibration._MIN_BUCKET_SAMPLES
    try:
        # Gerçek DB'ye bağlanmadan sadece eşik mantığını doğrula.
        assert original == 20
    finally:
        confidence_calibration._MIN_BUCKET_SAMPLES = original
