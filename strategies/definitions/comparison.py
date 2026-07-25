"""Strateji karşılaştırma motoru."""

class StrategyComparator:
    @staticmethod
    def compare(results: dict[str, dict]) -> dict:
        metrics = {}
        for name, res in results.items():
            metrics[name] = {
                "sharpe": res.get("sharpe", 0.0),
                "max_dd": res.get("max_drawdown", 0.0),
                "win_rate": res.get("win_rate", 0.0),
                "profit_factor": res.get("profit_factor", 0.0),
            }
        best = max(metrics, key=lambda k: metrics[k]["sharpe"])
        return {"best_strategy": best, "metrics": metrics}
