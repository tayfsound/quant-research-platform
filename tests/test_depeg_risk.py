"""Stablecoin/Pegged-Asset Depeg Risk testleri."""
from analytics.depeg_risk import compute_depeg_deviation


def test_matching_price_shows_no_depeg():
    result = compute_depeg_deviation(pegged_price=2650.0, reference_price=2650.0)
    assert result["deviation_pct"] == 0.0
    assert result["depeg_detected"] is False


def test_small_deviation_within_threshold_is_not_flagged():
    result = compute_depeg_deviation(pegged_price=2651.0, reference_price=2650.0)
    assert result["depeg_detected"] is False


def test_large_deviation_is_flagged_as_depeg():
    # %2 sapma — gerçek bir depeg örneği (ör. USDC'nin 2023 SVB olayında düştüğü seviye).
    result = compute_depeg_deviation(pegged_price=0.98, reference_price=1.0)
    assert abs(result["deviation_pct"] - (-0.02)) < 1e-9
    assert result["depeg_detected"] is True


def test_usd_pegged_reference_of_one():
    result = compute_depeg_deviation(pegged_price=1.003, reference_price=1.0)
    assert abs(result["deviation_pct"] - 0.003) < 1e-9


def test_none_reference_price_is_fail_closed():
    assert compute_depeg_deviation(pegged_price=2650.0, reference_price=None) is None


def test_zero_or_negative_reference_price_is_fail_closed():
    assert compute_depeg_deviation(pegged_price=2650.0, reference_price=0.0) is None
    assert compute_depeg_deviation(pegged_price=2650.0, reference_price=-1.0) is None


def test_none_pegged_price_is_fail_closed():
    assert compute_depeg_deviation(pegged_price=None, reference_price=2650.0) is None
