"""Sprint 9: Portfolio-level Decision Fusion — combines already-decided
per-symbol position sizes into a portfolio-VaR-checked allocation.

This does NOT re-decide direction/size per symbol (that's still
CognitiveEngine.run(), one call per symbol/bar, per Sprint 5) and it does
NOT loosen or bypass risk/limits/portfolio.py's check — it can only scale
proposed sizes DOWN to fit within the portfolio VaR limit, mirroring the
single-symbol rule that signal/AI code can propose but only risk/ code can
approve.
"""
from dataclasses import dataclass

import numpy as np

from risk.limits.portfolio import PortfolioRiskEngine


@dataclass
class PortfolioFusionResult:
    final_sizes: dict[str, float]
    portfolio_var_before: float
    portfolio_var_after: float
    scaled_down: bool


class PortfolioFusionStage:
    def __init__(self, risk_engine: PortfolioRiskEngine | None = None):
        self.risk_engine = risk_engine or PortfolioRiskEngine()

    def fuse(
        self,
        proposed_sizes: dict[str, float],
        returns: dict[str, list[float]],
        portfolio_value: float,
        max_var: float,
    ) -> PortfolioFusionResult:
        """
        proposed_sizes: {symbol: signed weight (fraction of portfolio_value)}
            — the per-symbol CognitiveEngine decisions, already converted to
            portfolio weights.
        returns: {symbol: [period_return, ...]} — same symbols, used to
            build the covariance matrix that captures correlation risk.
        """
        symbols, cov = self.risk_engine.covariance_matrix(
            {s: returns[s] for s in proposed_sizes}
        )
        weights = np.array([proposed_sizes[s] for s in symbols])

        result = self.risk_engine.check_portfolio_var_limit(weights, cov, portfolio_value, max_var)

        if result.approved:
            return PortfolioFusionResult(
                final_sizes=dict(zip(symbols, weights.tolist())),
                portfolio_var_before=result.portfolio_var,
                portfolio_var_after=result.portfolio_var,
                scaled_down=False,
            )

        # Portfolio VaR (a quadratic form in weights) scales linearly with a
        # uniform scalar applied to every weight, so this scale factor brings
        # portfolio_var down to exactly max_var, not just "roughly under it".
        scale = max_var / result.portfolio_var if result.portfolio_var > 0 else 0.0
        scaled_weights = weights * scale

        return PortfolioFusionResult(
            final_sizes=dict(zip(symbols, scaled_weights.tolist())),
            portfolio_var_before=result.portfolio_var,
            portfolio_var_after=max_var,
            scaled_down=True,
        )
