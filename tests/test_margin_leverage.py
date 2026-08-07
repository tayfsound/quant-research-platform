"""Faz 255: kaldıraç + likidasyon fiyatı testleri."""
from simulator.margin import compute_liquidation_price


def test_spot_position_has_no_liquidation_price():
    assert compute_liquidation_price(100.0, "LONG", leverage=1.0) is None
    assert compute_liquidation_price(100.0, "LONG", leverage=None) is None


def test_long_liquidation_price_is_below_entry():
    liq = compute_liquidation_price(100.0, "LONG", leverage=10.0, maintenance_margin_rate=0.005)
    # entry * (1 - 1/10 + 0.005) = 100 * 0.905 = 90.5
    assert abs(liq - 90.5) < 1e-9
    assert liq < 100.0


def test_short_liquidation_price_is_above_entry():
    liq = compute_liquidation_price(100.0, "SHORT", leverage=10.0, maintenance_margin_rate=0.005)
    # entry * (1 + 1/10 - 0.005) = 100 * 1.095 = 109.5
    assert abs(liq - 109.5) < 1e-9
    assert liq > 100.0


def test_higher_leverage_means_closer_liquidation():
    liq_5x = compute_liquidation_price(100.0, "LONG", leverage=5.0)
    liq_20x = compute_liquidation_price(100.0, "LONG", leverage=20.0)
    assert liq_20x > liq_5x  # 20x'te likidasyon fiyatı entry'ye daha yakın (daha az düşüşle tetiklenir)
