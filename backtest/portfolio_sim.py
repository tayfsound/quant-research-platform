"""Çoklu strateji portföy simülasyonu."""

class PortfolioSimulator:
    def __init__(self, initial_capital: float = 100_000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital

    def simulate(self, fills_by_strategy: dict[str, list[dict]]) -> dict:
        results = {}
        for strategy_name, fills in fills_by_strategy.items():
            pnl = sum(f.get("pnl", 0.0) for f in fills)
            results[strategy_name] = {"pnl": pnl, "num_trades": len(fills)}
        return results
