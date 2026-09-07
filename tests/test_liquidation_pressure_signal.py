"""analytics/liquidation_pressure_signal.py — Faz 439 (2026-09-08). Bu
ortamda `liquidation_events` hep 0 satır olduğu için (coğrafi WS kısıtı,
MempoolAgent/BehavioralAgent İLE AYNI) girdiler SENTETİK/MOCK — üretim
sunucusunda gerçek veriyle AYRICA doğrulanmalı."""
from analytics.liquidation_pressure_signal import compute_liquidation_pressure_signal


def test_below_min_total_is_no_data():
    pressure = {"long_liquidated_usd": 500.0, "short_liquidated_usd": 200.0}
    result = compute_liquidation_pressure_signal(pressure)
    assert result["category"] == "no_data"


def test_long_dominant_when_long_liquidations_at_least_double_short():
    pressure = {"long_liquidated_usd": 40_000.0, "short_liquidated_usd": 10_000.0}
    result = compute_liquidation_pressure_signal(pressure)
    assert result["category"] == "long_liquidation_dominant"
    assert result["long_short_ratio"] == 4.0


def test_short_dominant_when_short_liquidations_at_least_double_long():
    pressure = {"long_liquidated_usd": 10_000.0, "short_liquidated_usd": 50_000.0}
    result = compute_liquidation_pressure_signal(pressure)
    assert result["category"] == "short_liquidation_dominant"


def test_balanced_when_neither_side_dominates():
    pressure = {"long_liquidated_usd": 30_000.0, "short_liquidated_usd": 25_000.0}
    result = compute_liquidation_pressure_signal(pressure)
    assert result["category"] == "balanced"


def test_missing_fields_default_to_zero_and_are_no_data():
    assert compute_liquidation_pressure_signal({})["category"] == "no_data"


def test_long_short_ratio_is_none_when_no_short_liquidations():
    pressure = {"long_liquidated_usd": 20_000.0, "short_liquidated_usd": 0.0}
    result = compute_liquidation_pressure_signal(pressure)
    assert result["category"] == "long_liquidation_dominant"
    assert result["long_short_ratio"] is None
