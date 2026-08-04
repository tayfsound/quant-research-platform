"""Sprint 9: portfolio-level decision fusion — unit tests with hand-verified
scaling math, plus the Faz 171 gate: 3+ asset classes paper-traded together
with the portfolio VaR limit genuinely enforced (not just present in code)."""
import numpy as np
import pytest

from risk.limits.portfolio import PortfolioRiskEngine
from services.portfolio_fusion import PortfolioFusionStage

RETURNS_A = [0.02, -0.02, 0.02, -0.02]
RETURNS_B = [0.04, -0.04, 0.04, -0.04]  # perfectly correlated with A


def test_fusion_passes_through_unscaled_when_under_limit():
    stage = PortfolioFusionStage()
    result = stage.fuse(
        proposed_sizes={"A": 0.5, "B": 0.5},
        returns={"A": RETURNS_A, "B": RETURNS_B},
        portfolio_value=100_000.0,
        max_var=10_000.0,  # portfolio_var is 4935 (see test_portfolio_risk_engine) -> under limit
    )
    assert result.scaled_down is False
    assert result.final_sizes == pytest.approx({"A": 0.5, "B": 0.5})
    assert result.portfolio_var_before == pytest.approx(4935.0)


def test_fusion_scales_down_proportionally_to_exactly_hit_the_limit():
    stage = PortfolioFusionStage()
    result = stage.fuse(
        proposed_sizes={"A": 0.5, "B": 0.5},
        returns={"A": RETURNS_A, "B": RETURNS_B},
        portfolio_value=100_000.0,
        max_var=1000.0,  # well under the 4935 unscaled VaR
    )
    assert result.scaled_down is True
    assert result.portfolio_var_before == pytest.approx(4935.0)
    assert result.portfolio_var_after == pytest.approx(1000.0)

    # both weights scaled by the SAME factor (proportional, not arbitrary)
    scale_a = result.final_sizes["A"] / 0.5
    scale_b = result.final_sizes["B"] / 0.5
    assert scale_a == pytest.approx(scale_b)

    # re-running the scaled weights through the risk engine directly must
    # independently reproduce max_var, not just trust the scale arithmetic
    engine = PortfolioRiskEngine()
    _, cov = engine.covariance_matrix({"A": RETURNS_A, "B": RETURNS_B})
    scaled_weights = np.array([result.final_sizes["A"], result.final_sizes["B"]])
    recomputed_var = engine.portfolio_var(scaled_weights, cov, 100_000.0)
    assert recomputed_var == pytest.approx(1000.0)


def test_three_plus_asset_classes_paper_traded_with_portfolio_var_enforced():
    """Faz 171 gate: 3+ asset classes at once, portfolio VaR limit genuinely
    applied — approves a diversified allocation, rejects/scales an
    over-concentrated one, using real generated OHLCV across asset classes."""
    from market_data.multi_asset_dataset import asset_classes_represented, generate_multi_asset_dataset

    symbols = ["BTCUSDT", "XAUUSD", "NASDAQ", "US10Y"]
    assert len(asset_classes_represented(symbols)) >= 3

    data = generate_multi_asset_dataset(symbols, bars=60, seed=7)
    returns = {}
    for sym, bars in data.items():
        closes = [b.close for b in bars]
        returns[sym] = [(closes[i + 1] - closes[i]) / closes[i] for i in range(len(closes) - 1)]

    stage = PortfolioFusionStage()

    # Modest, diversified allocation -> should fit comfortably under a generous limit.
    diversified = stage.fuse(
        proposed_sizes={s: 0.1 for s in symbols},
        returns=returns,
        portfolio_value=100_000.0,
        max_var=50_000.0,
    )
    assert diversified.scaled_down is False

    # Same aggressive allocation against a tight limit -> must be scaled
    # down, not silently allowed through.
    concentrated = stage.fuse(
        proposed_sizes={s: 1.0 for s in symbols},
        returns=returns,
        portfolio_value=100_000.0,
        max_var=1_000.0,
    )
    assert concentrated.scaled_down is True
    assert concentrated.portfolio_var_after == pytest.approx(1_000.0)
    assert concentrated.portfolio_var_before > 1_000.0
