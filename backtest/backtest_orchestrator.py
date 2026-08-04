"""Sprint 6: run a cognitive backtest, compute the full metrics set, and
persist the result as Class 2 data (backtest_runs — never deleted, so a
run's numbers can always be independently re-verified later)."""
import math

from analytics.metrics.engine import MetricsEngine
from backtest.cognitive_backtest_runner import run_cognitive_backtest
from contracts.backtest_run import BacktestRun
from contracts.experiment_registry import ExperimentRegistry
from database.repositories.backtest_run_repository import BacktestRunRepository
from market_data.ingestion.ohlcv import OHLCV

INITIAL_CAPITAL = 100_000.0


def _sanitize(value):
    """JSON (and Postgres' json column) rejects Infinity/NaN — replace with
    None rather than silently persisting a value that would corrupt the row
    or crash on write."""
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        return None
    return value


def run_and_persist_backtest(
    data: dict[str, list[OHLCV]],
    session,
    pinned_weight_snapshot_id=None,
    fee: float = 0.001,
    lookback: int = 3,
) -> BacktestRun:
    result = run_cognitive_backtest(
        data, pinned_weight_snapshot_id=pinned_weight_snapshot_id, fee=fee, lookback=lookback
    )

    equity = [INITIAL_CAPITAL] + [INITIAL_CAPITAL + p for p in result.equity_curve.tolist()]
    period_pnls = [equity[i + 1] - equity[i] for i in range(len(equity) - 1)]
    fills = [{"pnl": p} for p in period_pnls]

    metrics = {
        "sharpe_ratio": MetricsEngine.sharpe_ratio(period_pnls),
        "sortino_ratio": MetricsEngine.sortino_ratio(period_pnls),
        "max_drawdown": MetricsEngine.max_drawdown(equity),
        "calmar_ratio": MetricsEngine.calmar_ratio(period_pnls, equity),
        "mar_ratio": MetricsEngine.mar_ratio(period_pnls, equity),
        "ulcer_index": MetricsEngine.ulcer_index(equity),
        "recovery_factor": MetricsEngine.recovery_factor(equity),
        "win_rate": MetricsEngine.win_rate(fills),
        "profit_factor": MetricsEngine.profit_factor(fills),
        "expectancy": MetricsEngine.expectancy(fills),
    }
    metrics = {k: _sanitize(v) for k, v in metrics.items()}

    run = BacktestRun(
        symbols=result.symbols,
        git_sha=ExperimentRegistry.get_git_sha(),
        weight_snapshot_id=pinned_weight_snapshot_id,
        fee=fee,
        lookback=lookback,
        num_bars=result.num_bars,
        total_pnl=result.total_pnl,
        per_symbol_pnl=result.per_symbol_pnl,
        metrics=metrics,
        equity_curve=[_sanitize(v) for v in equity],
    )

    return BacktestRunRepository(session).save(run)
