"""Equity eğrisi ve drawdown analizi."""
import numpy as np


class EquityAnalytics:
    @staticmethod
    def compute_equity(initial: float, fills: list[dict]) -> list[float]:
        equity = [initial]
        for f in fills:
            equity.append(equity[-1] + f.get("pnl", 0.0))
        return equity

    @staticmethod
    def drawdown_series(equity: list[float]) -> list[float]:
        peak = np.maximum.accumulate(equity)
        return ((np.array(equity) - peak) / peak).tolist()

    @staticmethod
    def underwater_periods(equity: list[float]) -> list[dict]:
        dd = np.array(EquityAnalytics.drawdown_series(equity))
        periods = []
        in_dd = False
        start = 0
        for i, v in enumerate(dd):
            if v < 0 and not in_dd:
                start = i
                in_dd = True
            elif v >= 0 and in_dd:
                periods.append({"start": start, "end": i, "duration": i - start, "max_dd": float(min(dd[start:i]))})
                in_dd = False
        return periods
