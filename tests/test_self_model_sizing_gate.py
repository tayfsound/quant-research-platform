"""analytics/self_model_sizing_gate.py — kullanıcı bulgusu (2026-08-28):
"Kill Switch aktif olduğu halde self control kapalı gibi görünüyor" —
Self-Model'in overall_reliability'si artık pozisyon boyutuna bağlı."""
from analytics.self_model_sizing_gate import (
    DEGRADED_MULTIPLIER,
    UNTRUSTWORTHY_MULTIPLIER,
    self_model_size_multiplier,
)


def test_full_size_when_high():
    assert self_model_size_multiplier("high") == 1.0


def test_full_size_when_none():
    assert self_model_size_multiplier(None) == 1.0


def test_full_size_when_unknown_value():
    assert self_model_size_multiplier("some_unexpected_value") == 1.0


def test_shrinks_on_degraded():
    assert self_model_size_multiplier("degraded") == DEGRADED_MULTIPLIER


def test_shrinks_more_on_untrustworthy():
    assert self_model_size_multiplier("untrustworthy") == UNTRUSTWORTHY_MULTIPLIER


def test_untrustworthy_is_stricter_than_degraded():
    assert self_model_size_multiplier("untrustworthy") < self_model_size_multiplier("degraded")
