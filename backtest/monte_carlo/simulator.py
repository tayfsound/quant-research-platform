"""Monte Carlo simülasyonu."""
import numpy as np


class MonteCarloSimulator:
    def __init__(self, returns: list[float], num_simulations: int = 1000, horizon: int = 30):
        self.returns = np.array(returns)
        self.num_simulations = num_simulations
        self.horizon = horizon

    def run(self) -> dict:
        mean = np.mean(self.returns)
        std = np.std(self.returns)
        simulations = np.random.normal(mean, std, (self.num_simulations, self.horizon))
        cumulative = np.cumprod(1 + simulations, axis=1)
        final_values = cumulative[:, -1]
        var_95 = np.percentile(final_values, 5)
        cvar_95 = np.mean(final_values[final_values <= var_95])
        return {
            "expected_final": float(np.mean(final_values)),
            "var_95": float(var_95),
            "cvar_95": float(cvar_95),
            "max_drawdown_prob": float(np.mean(final_values < 1.0)),
        }
