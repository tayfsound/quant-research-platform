"""Sprint 8: portfolio-level risk — covariance matrix, portfolio VaR,
correlation-adjusted position checks. An EXTENSION of risk/limits/, not a
parallel system: single-symbol authority stays in engines/risk_engine.py
(RiskEngine) and engines/cognitive_pipeline.py (RiskGateStage); this adds
the cross-symbol layer those can't see. AI/learning code must not import
this to change its output — same "signal can't move the limits" rule as
the single-symbol risk layer.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class PortfolioVarResult:
    portfolio_var: float
    max_var: float
    approved: bool


class PortfolioRiskEngine:
    def __init__(self, z_score: float = 1.645):
        """z_score=1.645 is the one-tailed 95% normal quantile — the
        standard parametric (variance-covariance) VaR assumption."""
        self.z_score = z_score

    def covariance_matrix(self, returns: dict[str, list[float]]) -> tuple[list[str], np.ndarray]:
        """returns: {symbol: [period_return, ...]} — all series same length.
        Population covariance (bias=True / divide by N), matching this
        project's other statistics (analytics/metrics/engine.py uses
        population std throughout, not sample)."""
        symbols = list(returns.keys())
        lengths = {len(v) for v in returns.values()}
        if len(lengths) != 1:
            raise ValueError(f"all symbols must have the same number of return periods, got {lengths}")
        matrix = np.array([returns[s] for s in symbols])
        cov = np.cov(matrix, bias=True)
        if cov.ndim == 0:
            cov = cov.reshape(1, 1)
        return symbols, cov

    def portfolio_variance(self, weights: np.ndarray, cov: np.ndarray) -> float:
        return float(weights @ cov @ weights)

    def portfolio_var(self, weights: np.ndarray, cov: np.ndarray, portfolio_value: float) -> float:
        """Parametric 1-period VaR in $ — how much the portfolio could lose
        at the given confidence level, capturing cross-symbol correlation
        through the covariance matrix (two correlated positions produce a
        higher portfolio VaR than the same notional split across
        uncorrelated ones — this IS the "korelasyon-ayarlı" part)."""
        variance = self.portfolio_variance(weights, cov)
        std = float(np.sqrt(max(variance, 0.0)))
        return self.z_score * std * portfolio_value

    def check_portfolio_var_limit(
        self,
        weights: np.ndarray,
        cov: np.ndarray,
        portfolio_value: float,
        max_var: float,
    ) -> PortfolioVarResult:
        var = self.portfolio_var(weights, cov, portfolio_value)
        return PortfolioVarResult(portfolio_var=var, max_var=max_var, approved=var <= max_var)
