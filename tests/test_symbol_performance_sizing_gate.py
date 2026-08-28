"""analytics/symbol_performance_sizing_gate.py — kullanıcı bulgusu (Grok
raporu doğrulaması): council SL zararları belirli sembol×yön hücrelerinde
sistematik olarak yoğunlaşıyor. Kara liste DEĞİL, boyut küçültme
(kullanıcı kararı)."""
from analytics.symbol_performance_sizing_gate import (
    MIN_MULTIPLIER,
    symbol_direction_size_multiplier,
)


def test_full_size_when_no_data():
    assert symbol_direction_size_multiplier(None, None, 0.74) == 1.0


def test_full_size_when_too_few_samples():
    assert symbol_direction_size_multiplier(0.1, 5, 0.74) == 1.0


def test_full_size_when_at_or_above_baseline():
    assert symbol_direction_size_multiplier(0.8, 40, 0.74) == 1.0
    assert symbol_direction_size_multiplier(0.74, 40, 0.74) == 1.0


def test_reduces_proportionally_for_real_atom_long_event():
    """Gerçek olay: ATOMUSDT_LONG n=41, win_rate=%31.7."""
    result = symbol_direction_size_multiplier(0.3171, 41, 0.74)
    assert abs(result - (0.3171 / 0.74)) < 1e-6


def test_never_drops_below_floor():
    assert symbol_direction_size_multiplier(0.05, 40, 0.74) == MIN_MULTIPLIER


def test_full_size_when_baseline_is_zero():
    assert symbol_direction_size_multiplier(0.3, 40, 0.0) == 1.0
