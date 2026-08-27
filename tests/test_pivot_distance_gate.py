"""analytics/pivot_distance_gate.py — backlog #17."""
from analytics.pivot_distance_gate import (
    compute_nearest_pivot_distance_pct,
    is_pivot_distance_entry_blocked,
)


def _levels(**kwargs):
    return {"P": 100.0, "R1": 102.0, "R2": 104.0, "R3": 106.0, "S1": 98.0, "S2": 96.0, "S3": 94.0, **kwargs}


def test_finds_distance_to_nearest_of_seven_levels():
    dist = compute_nearest_pivot_distance_pct(_levels(), current_price=102.5)
    # En yakın seviye R1=102.0, mesafe = 0.5/102.5
    assert abs(dist - (0.5 / 102.5)) < 1e-9


def test_missing_levels_is_fail_open_not_fail_closed():
    assert compute_nearest_pivot_distance_pct(None, current_price=100.0) is None
    assert compute_nearest_pivot_distance_pct({}, current_price=100.0) is None


def test_zero_or_negative_price_returns_none():
    assert compute_nearest_pivot_distance_pct(_levels(), current_price=0.0) is None


def test_blocks_only_when_large_cap_and_far():
    assert is_pivot_distance_entry_blocked(True, 0.01, threshold_pct=0.006) is True
    assert is_pivot_distance_entry_blocked(True, 0.003, threshold_pct=0.006) is False
    # small-cap'te gerçek veri TERS/YOK desen gösterdi — hiç engellenmez
    assert is_pivot_distance_entry_blocked(False, 0.05, threshold_pct=0.006) is False


def test_missing_distance_never_blocks():
    assert is_pivot_distance_entry_blocked(True, None, threshold_pct=0.006) is False
