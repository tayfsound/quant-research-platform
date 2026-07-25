"""Performans metrikleri."""
import numpy as np


class MetricsEngine:
    @staticmethod
    def sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
        arr = np.array(returns)
        excess = np.mean(arr) - risk_free
        std = np.std(arr)
        return excess / std if std > 0 else 0.0

    @staticmethod
    def sortino_ratio(returns: list[float], risk_free: float = 0.0) -> float:
        arr = np.array(returns)
        downside = arr[arr < 0]
        std_down = np.std(downside) if len(downside) > 0 else 0.0001
        return (np.mean(arr) - risk_free) / std_down

    @staticmethod
    def max_drawdown(equity: list[float]) -> float:
        peak = np.maximum.accumulate(equity)
        drawdown = (np.array(equity) - peak) / peak
        return float(np.min(drawdown))

    @staticmethod
    def calmar_ratio(returns: list[float], equity: list[float]) -> float:
        cagr = (equity[-1] / equity[0]) ** (1 / len(equity)) - 1 if equity[0] > 0 else 0.0
        mdd = abs(MetricsEngine.max_drawdown(equity))
        return cagr / mdd if mdd > 0 else 0.0

    @staticmethod
    def var_95(returns: list[float]) -> float:
        return float(np.percentile(returns, 5))

    @staticmethod
    def win_rate(fills: list[dict]) -> float:
        wins = [f for f in fills if f.get("pnl", 0) > 0]
        return len(wins) / len(fills) if fills else 0.0

    @staticmethod
    def profit_factor(fills: list[dict]) -> float:
        gross_profit = sum(f.get("pnl", 0) for f in fills if f.get("pnl", 0) > 0)
        gross_loss = abs(sum(f.get("pnl", 0) for f in fills if f.get("pnl", 0) < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")
