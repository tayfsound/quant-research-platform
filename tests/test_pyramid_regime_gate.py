"""Faz 361 — analytics/pyramid_regime_gate.py saf fonksiyon testleri."""
from analytics.pyramid_regime_gate import is_worse_price_pyramid_blocked


def test_no_existing_position_is_never_blocked():
    assert not is_worse_price_pyramid_blocked("LONG", 100.0, None, "bearish_normal")


def test_long_worse_price_blocked_outside_allowed_regime():
    assert is_worse_price_pyramid_blocked("LONG", 110.0, 100.0, "bearish_normal")


def test_long_worse_price_allowed_in_bullish_low():
    assert not is_worse_price_pyramid_blocked("LONG", 110.0, 100.0, "bullish_low")


def test_long_better_price_never_blocked_regardless_of_regime():
    assert not is_worse_price_pyramid_blocked("LONG", 90.0, 100.0, "bearish_high")


def test_short_worse_price_blocked_outside_allowed_regime():
    # SHORT icin "daha kotu fiyat" = daha DUSUK fiyattan girmek (mevcut
    # ortalamanin altinda kar potansiyeli daha az kaliyor).
    assert is_worse_price_pyramid_blocked("SHORT", 90.0, 100.0, "bearish_high")


def test_short_worse_price_allowed_in_bullish_low():
    assert not is_worse_price_pyramid_blocked("SHORT", 90.0, 100.0, "bullish_low")


def test_short_better_price_never_blocked():
    assert not is_worse_price_pyramid_blocked("SHORT", 110.0, 100.0, "bearish_high")


def test_unknown_regime_fails_closed_to_blocked():
    assert is_worse_price_pyramid_blocked("LONG", 110.0, 100.0, None)
    assert is_worse_price_pyramid_blocked("LONG", 110.0, 100.0, "unknown")


def test_custom_allowed_regime_is_respected():
    assert not is_worse_price_pyramid_blocked(
        "LONG", 110.0, 100.0, "bearish_low", allowed_regime="bearish_low"
    )
