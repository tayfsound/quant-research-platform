"""Faz 255: kaldıraç + likidasyon fiyatı testleri."""
from simulator.margin import compute_liquidation_price, max_safe_leverage


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


def test_max_safe_leverage_none_when_stop_distance_unknown():
    assert max_safe_leverage(None) is None
    assert max_safe_leverage(0.0) is None


def test_max_safe_leverage_keeps_liquidation_at_least_1_5x_the_stop_distance():
    """Faz 260: kullanıcı bulgusu — yüksek kaldıraç + geniş ATR'de
    likidasyon, stop-loss'tan önce tetiklenebiliyordu."""
    stop_distance_pct = 0.0536  # gerçek ölçülen BTCUSDT 2.5x günlük ATR stop mesafesi
    lev = max_safe_leverage(stop_distance_pct)

    liq_distance_at_max_lev = 1.0 / lev
    assert liq_distance_at_max_lev >= stop_distance_pct * 1.5 - 1e-9


def test_max_safe_leverage_is_capped_at_exchange_max():
    # Çok küçük bir stop mesafesi teorik olarak 125x'in üzerini önerebilir
    # — gerçek borsa sınırının üzerine hiç çıkılmamalı.
    assert max_safe_leverage(0.0001) == 125.0


def test_wider_atr_means_lower_max_safe_leverage():
    tight = max_safe_leverage(0.02)
    wide = max_safe_leverage(0.14)  # gerçek ölçülen ADAUSDT stop mesafesi
    assert wide < tight
