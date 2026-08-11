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
        """Faz 268an — gerçek bulgu: tam olarak BİR kayıp içeren bir
        dönüşte (ör. tek işlemlik bir backtest) downside dizisi tek
        elemanlı oluyor, np.std([tek_değer]) matematiksel olarak tam
        0.0 — önceki kod bunu SADECE downside hiç yoksa (0.0001 sabit
        payda) koruyordu, tek elemanlı gerçek-sıfır std'yi kaçırıyordu.
        Sonuç: bölme -Infinity/Infinity üretti, bu da backtest_runs.
        metrics'e (Postgres JSON — Infinity kabul etmiyor) yazılırken
        gerçek bir DataError'a yol açtı. sharpe_ratio ile AYNI, kanıtlanmış
        fail-closed desen: payda sıfırsa (ya da tanımsızsa) 0.0."""
        arr = np.array(returns)
        downside = arr[arr < 0]
        std_down = np.std(downside) if len(downside) > 0 else 0.0
        excess = np.mean(arr) - risk_free
        return float(excess / std_down) if std_down > 0 else 0.0

    @staticmethod
    def max_drawdown(equity: list[float]) -> float:
        peak = np.maximum.accumulate(equity)
        drawdown = (np.array(equity) - peak) / peak
        return float(np.min(drawdown))

    @staticmethod
    def calmar_ratio(returns: list[float], equity: list[float], periods_per_year: int = 252) -> float:
        """CAGR / |max drawdown|. periods_per_year annualizes the bar count
        (252 for daily bars, 8760 for hourly, etc.) — using raw bar count
        instead of years would silently understate CAGR for anything but
        yearly bars."""
        n = len(equity) - 1
        cagr = (equity[-1] / equity[0]) ** (periods_per_year / n) - 1 if equity[0] > 0 and n > 0 else 0.0
        mdd = abs(MetricsEngine.max_drawdown(equity))
        return cagr / mdd if mdd > 0 else 0.0

    @staticmethod
    def mar_ratio(returns: list[float], equity: list[float], periods_per_year: int = 252) -> float:
        """Same CAGR/|max drawdown| formula as calmar_ratio — MAR conventionally
        uses full-history CAGR vs. Calmar's rolling 3-year window, a
        distinction this engine doesn't model (no rolling window here), but
        both are exposed since the roadmap lists them as separate metrics."""
        return MetricsEngine.calmar_ratio(returns, equity, periods_per_year)

    @staticmethod
    def ulcer_index(equity: list[float]) -> float:
        """sqrt(mean(drawdown_pct^2)) — penalizes deep AND long drawdowns,
        unlike max_drawdown which only looks at the single worst point."""
        from analytics.metrics.equity import EquityAnalytics
        dd = np.array(EquityAnalytics.drawdown_series(equity))
        return float(np.sqrt(np.mean(dd**2)))

    @staticmethod
    def recovery_factor(equity: list[float]) -> float:
        """Total net profit ($) / max drawdown ($) — how much profit was
        made per dollar of the worst peak-to-trough loss."""
        peak = np.maximum.accumulate(equity)
        max_dd_dollar = float(np.max(np.array(peak) - np.array(equity)))
        total_profit = equity[-1] - equity[0]
        return total_profit / max_dd_dollar if max_dd_dollar > 0 else float("inf")

    @staticmethod
    def expectancy(fills: list[dict]) -> float:
        """(win_rate * avg_win) - (loss_rate * avg_loss) — expected pnl per trade."""
        if not fills:
            return 0.0
        pnls = [f.get("pnl", 0.0) for f in fills]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls)
        loss_rate = len(losses) / len(pnls)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        return win_rate * avg_win - loss_rate * avg_loss

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
