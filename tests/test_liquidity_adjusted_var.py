"""Liquidity-Adjusted VaR (Bangia et al. 1999) testleri."""
from analytics.liquidity_adjusted_var import compute_liquidity_adjusted_var, compute_liquidity_cost


def test_liquidity_cost_matches_the_bangia_formula_by_hand():
    # spread hep 100 bps (%1) sabit -> std=0, formül basitleşiyor.
    spread_bps = [100.0] * 20
    result = compute_liquidity_cost(spread_bps, position_value=10_000.0, z_score=1.645)
    expected = 0.5 * 10_000.0 * 0.01  # mean_spread_pct = 0.01, std=0
    assert abs(result["liquidity_cost"] - expected) < 1e-6
    assert abs(result["mean_spread_bps"] - 100.0) < 1e-6
    assert result["std_spread_bps"] == 0.0


def test_liquidity_cost_is_none_below_min_sample_size():
    result = compute_liquidity_cost([50.0] * 5, position_value=10_000.0)
    assert result is None


def test_higher_and_more_volatile_spread_produces_higher_liquidity_cost():
    stable = compute_liquidity_cost([50.0] * 20, position_value=10_000.0)
    volatile = compute_liquidity_cost([10.0, 200.0] * 10, position_value=10_000.0)
    assert volatile["liquidity_cost"] > stable["liquidity_cost"]


def test_liquidity_adjusted_var_adds_cost_on_top_of_price_var():
    result = compute_liquidity_adjusted_var(
        price_var=500.0, spread_bps_series=[100.0] * 20, position_value=10_000.0, z_score=1.645,
    )
    assert result["price_var"] == 500.0
    assert result["liquidity_cost"] is not None
    assert abs(result["liquidity_adjusted_var"] - (500.0 + result["liquidity_cost"])) < 1e-6


def test_liquidity_adjusted_var_falls_back_to_price_var_when_spread_data_is_insufficient():
    """Fail-closed: yetersiz spread verisinden icat edilmiş bir likidite
    maliyeti üretilmez, ama fiyat-riski hesabı sessizce kaybolmaz."""
    result = compute_liquidity_adjusted_var(
        price_var=500.0, spread_bps_series=[100.0, 90.0], position_value=10_000.0,
    )
    assert result["liquidity_cost"] is None
    assert result["liquidity_adjusted_var"] == 500.0
