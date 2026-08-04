"""Sprint 8: portfolio risk engine — covariance/VaR checked against
hand-computed reference values, not just "code says X, assert X"."""
import numpy as np
import pytest

from risk.limits.portfolio import PortfolioRiskEngine

# A perfectly correlated with B (B = 2*A always):
#   var(A) = mean([0.02^2, 0.02^2, 0.02^2, 0.02^2]) = 0.0004
#   var(B) = mean([0.04^2]*4)                        = 0.0016
#   cov(A,B) = mean([0.02*0.04]*4)                    = 0.0008
RETURNS_A = [0.02, -0.02, 0.02, -0.02]
RETURNS_B = [0.04, -0.04, 0.04, -0.04]  # 2x A, perfectly correlated
RETURNS_C = [0.01, 0.01, -0.01, -0.01]  # uncorrelated with A: mean(A*C) = 0 exactly


def test_covariance_matrix_matches_hand_computed_values():
    engine = PortfolioRiskEngine()
    symbols, cov = engine.covariance_matrix({"A": RETURNS_A, "B": RETURNS_B})

    assert symbols == ["A", "B"]
    expected = np.array([[0.0004, 0.0008], [0.0008, 0.0016]])
    assert cov == pytest.approx(expected)


def test_covariance_is_zero_for_uncorrelated_series():
    engine = PortfolioRiskEngine()
    _, cov = engine.covariance_matrix({"A": RETURNS_A, "C": RETURNS_C})
    assert cov[0, 1] == pytest.approx(0.0)


def test_portfolio_var_matches_hand_computed_value():
    # weights=[0.5,0.5]: portfolio_variance = 0.25*0.0004 + 2*0.25*0.0008 + 0.25*0.0016
    #                                        = 0.0001 + 0.0004 + 0.0004 = 0.0009
    # portfolio_std = sqrt(0.0009) = 0.03
    # VaR (z=1.645, portfolio_value=100_000) = 1.645 * 0.03 * 100_000 = 4935.0
    engine = PortfolioRiskEngine(z_score=1.645)
    _, cov = engine.covariance_matrix({"A": RETURNS_A, "B": RETURNS_B})
    weights = np.array([0.5, 0.5])

    var = engine.portfolio_var(weights, cov, portfolio_value=100_000.0)
    assert var == pytest.approx(4935.0)


def test_correlated_positions_produce_higher_var_than_uncorrelated_ones():
    """The whole point of covariance-based VaR: two correlated positions
    are riskier together than the same notional split across uncorrelated
    ones — this is the 'korelasyon-ayarlı' requirement itself."""
    engine = PortfolioRiskEngine()
    weights = np.array([0.5, 0.5])

    _, cov_correlated = engine.covariance_matrix({"A": RETURNS_A, "B": RETURNS_B})
    _, cov_uncorrelated = engine.covariance_matrix({"A": RETURNS_A, "C": RETURNS_C})

    var_correlated = engine.portfolio_var(weights, cov_correlated, 100_000.0)
    var_uncorrelated = engine.portfolio_var(weights, cov_uncorrelated, 100_000.0)

    assert var_correlated > var_uncorrelated


def test_check_portfolio_var_limit_rejects_when_over_and_approves_when_under():
    engine = PortfolioRiskEngine()
    _, cov = engine.covariance_matrix({"A": RETURNS_A, "B": RETURNS_B})
    weights = np.array([0.5, 0.5])

    rejected = engine.check_portfolio_var_limit(weights, cov, 100_000.0, max_var=1000.0)
    assert rejected.approved is False
    assert rejected.portfolio_var == pytest.approx(4935.0)

    approved = engine.check_portfolio_var_limit(weights, cov, 100_000.0, max_var=10_000.0)
    assert approved.approved is True
