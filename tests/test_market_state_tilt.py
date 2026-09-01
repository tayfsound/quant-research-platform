"""Faz 402 — Market State Confidence Eğimi testleri (Market State Katmanı
Faz 2). tests/test_moe_regime_router.py'deki AYNI desen."""
from analytics.market_state_tilt import compute_market_state_tilt


def test_reversing_with_full_confidence_hits_max_tilt():
    result = compute_market_state_tilt({"direction": "LONG", "confidence": 1.0, "reversing": True})
    assert result["direction"] == "LONG"
    assert abs(result["agreeing_weight"] - 1.3) < 1e-6
    assert abs(result["opposing_weight"] - 0.7) < 1e-6


def test_reversing_with_partial_confidence_scales_tilt_proportionally():
    result = compute_market_state_tilt({"direction": "SHORT", "confidence": 0.5, "reversing": True})
    assert abs(result["agreeing_weight"] - 1.15) < 1e-6
    assert abs(result["opposing_weight"] - 0.85) < 1e-6


def test_not_reversing_is_a_noop_regardless_of_confidence():
    result = compute_market_state_tilt({"direction": "LONG", "confidence": 0.9, "reversing": False})
    assert result["agreeing_weight"] == 1.0
    assert result["opposing_weight"] == 1.0
    assert result["direction"] is None


def test_neutral_direction_is_a_noop_even_if_reversing():
    result = compute_market_state_tilt({"direction": "NEUTRAL", "confidence": 0.9, "reversing": True})
    assert result["agreeing_weight"] == 1.0
    assert result["opposing_weight"] == 1.0
    assert result["direction"] is None


def test_zero_confidence_reversing_produces_no_real_tilt():
    result = compute_market_state_tilt({"direction": "LONG", "confidence": 0.0, "reversing": True})
    assert result["agreeing_weight"] == 1.0
    assert result["opposing_weight"] == 1.0


def test_confidence_is_clipped_to_unit_interval():
    result = compute_market_state_tilt({"direction": "SHORT", "confidence": 5.0, "reversing": True})
    assert abs(result["agreeing_weight"] - 1.3) < 1e-6


def test_missing_fields_default_to_noop():
    assert compute_market_state_tilt({}) == {"agreeing_weight": 1.0, "opposing_weight": 1.0, "direction": None}
