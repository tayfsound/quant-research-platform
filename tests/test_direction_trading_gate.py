"""analytics/direction_trading_gate.py — kullanıcı isteği (2026-08-28):
Dashboard'daki LONG/SHORT kazanma oranı kartlarına manuel aç/kapa."""
from analytics.direction_trading_gate import is_direction_trading_blocked


def test_direction_blocked_when_explicitly_false():
    assert is_direction_trading_blocked("SHORT", {"SHORT": False}) is True


def test_direction_not_blocked_when_true():
    assert is_direction_trading_blocked("SHORT", {"SHORT": True}) is False


def test_direction_fail_open_for_unmapped_direction():
    assert is_direction_trading_blocked("LONG", {}) is False


def test_direction_none_never_blocked():
    assert is_direction_trading_blocked(None, {"LONG": False, "SHORT": False}) is False


def test_direction_other_direction_unaffected():
    assert is_direction_trading_blocked("LONG", {"SHORT": False}) is False
