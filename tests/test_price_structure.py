"""Price Structure ve Market Geometry testleri — Faz 344-368 (Cognitive Core 2.0)."""
from datetime import UTC, datetime, timedelta

from market_data.features.price_structure import compute_support_resistance_zones
from market_data.ingestion.ohlcv import OHLCV


def _bar(i: int, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
        open=close, high=close + 0.05, low=close - 0.05, close=close, volume=100.0,
    )


def test_repeated_swing_high_forms_a_real_resistance_zone():
    # İki ayrı zirve, ikisi de ~100'e dokunuyor (window=3'lük yerel
    # tepe tespiti için her iki tarafında da yeterli bar var).
    closes = [90, 92, 94, 96, 98, 100, 98, 96, 94, 90, 92, 94, 96, 98, 100.1, 98, 96, 94, 90]
    bars = [_bar(i, c) for i, c in enumerate(closes)]
    result = compute_support_resistance_zones(bars, tolerance_pct=0.02, min_touches=2)
    assert len(result["resistance_zones"]) >= 1
    top_zone = result["resistance_zones"][0]
    assert abs(top_zone["level"] - 100) < 1.0
    assert top_zone["touches"] >= 2


def test_single_touch_is_excluded_below_min_touches():
    closes = [90, 95, 100, 95, 90, 85, 80, 85, 90]
    bars = [_bar(i, c) for i, c in enumerate(closes)]
    result = compute_support_resistance_zones(bars, tolerance_pct=0.01, min_touches=3)
    # Hiçbir seviye 3 kez test edilmedi.
    assert result["resistance_zones"] == []


def test_short_data_is_handled_fail_closed():
    bars = [_bar(i, 100.0) for i in range(5)]
    result = compute_support_resistance_zones(bars)
    assert result == {"support_zones": [], "resistance_zones": [], "current_price": None}


def test_zones_are_sorted_by_touch_count_descending():
    # 100 dört kez, 80 iki kez test ediliyor.
    closes = [100, 90, 100, 85, 100, 80, 100.1, 82, 80.1, 90, 99.9, 85, 80, 90]
    bars = [_bar(i, c) for i, c in enumerate(closes)]
    result = compute_support_resistance_zones(bars, tolerance_pct=0.02, min_touches=2)
    all_zones = result["resistance_zones"] + result["support_zones"]
    touches = [z["touches"] for z in all_zones]
    assert touches == sorted(touches, reverse=True) or len(all_zones) <= 1


def test_current_price_reflects_the_last_close():
    closes = [90, 95, 100, 95, 90, 96, 100, 95, 91, 97]
    bars = [_bar(i, c) for i, c in enumerate(closes)]
    result = compute_support_resistance_zones(bars)
    assert result["current_price"] == closes[-1]
