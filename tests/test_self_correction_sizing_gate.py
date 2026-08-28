"""analytics/self_correction_sizing_gate.py — kullanıcı kararı (2026-08-28):
LONG'un son dönem çöküşü tespit edildiğinde boyut küçültülsün, iptal
edilmesin."""
from analytics.self_correction_sizing_gate import (
    MIN_MULTIPLIER,
    self_correction_size_multiplier,
)


def test_full_size_when_segment_is_none():
    assert self_correction_size_multiplier(None) == 1.0


def test_full_size_when_hypothesis_still_valid():
    segment = {
        "hypothesis_still_valid": True, "significant_change": True,
        "original_win_rate": 0.9, "recent_win_rate": 0.5,
    }
    assert self_correction_size_multiplier(segment) == 1.0


def test_full_size_when_change_not_significant():
    segment = {
        "hypothesis_still_valid": False, "significant_change": False,
        "original_win_rate": 0.9, "recent_win_rate": 0.5,
    }
    assert self_correction_size_multiplier(segment) == 1.0


def test_reduces_proportionally_to_the_real_drop():
    """Gerçek LONG olayı: 96.4% -> 71.5%, oran ~0.7414."""
    segment = {
        "hypothesis_still_valid": False, "significant_change": True,
        "original_win_rate": 0.9642, "recent_win_rate": 0.7148,
    }
    result = self_correction_size_multiplier(segment)
    assert abs(result - (0.7148 / 0.9642)) < 1e-6


def test_never_drops_below_min_multiplier():
    segment = {
        "hypothesis_still_valid": False, "significant_change": True,
        "original_win_rate": 0.9, "recent_win_rate": 0.01,
    }
    assert self_correction_size_multiplier(segment) == MIN_MULTIPLIER


def test_never_boosts_above_1_even_if_recent_is_better():
    segment = {
        "hypothesis_still_valid": False, "significant_change": True,
        "original_win_rate": 0.5, "recent_win_rate": 0.9,
    }
    assert self_correction_size_multiplier(segment) == 1.0


def test_full_size_when_original_win_rate_is_zero():
    segment = {
        "hypothesis_still_valid": False, "significant_change": True,
        "original_win_rate": 0.0, "recent_win_rate": 0.5,
    }
    assert self_correction_size_multiplier(segment) == 1.0


def test_full_size_when_recent_win_rate_missing():
    segment = {
        "hypothesis_still_valid": False, "significant_change": True,
        "original_win_rate": 0.9, "recent_win_rate": None,
    }
    assert self_correction_size_multiplier(segment) == 1.0
