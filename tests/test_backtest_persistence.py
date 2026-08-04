"""Sprint 6 gate: run a backtest, prove it's persisted for real (Class 2,
backtest_runs table), deterministic on repeat with a pinned weight snapshot,
and that the metrics are actually correct — not just present."""
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backtest.backtest_orchestrator import run_and_persist_backtest
from database.repositories.backtest_run_repository import BacktestRunRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV


def _bars(closes: list[float]) -> list[OHLCV]:
    now = datetime.now(timezone.utc)
    return [
        OHLCV(timestamp=now + timedelta(minutes=i), open=c, high=c, low=c, close=c, volume=100.0)
        for i, c in enumerate(closes)
    ]


def _tiny_data():
    return {
        "BTCUSDT": _bars([100, 102, 101, 105, 107, 106, 110, 111]),
        "ETHUSDT": _bars([50, 49, 51, 52, 53, 52, 54, 55]),
    }


def _pinned_snapshot():
    from contracts.agent_weight_snapshot import AgentWeightSnapshot
    from services.weight_repository import WeightRepository

    storage_path = "test_backtest_persist_weight_history"
    shutil.rmtree(storage_path, ignore_errors=True)
    repo = WeightRepository(storage_path=storage_path)
    snapshot = repo.save(AgentWeightSnapshot(weights={"technical": 1.0}).finalize())
    return repo, snapshot, storage_path


def test_backtest_run_is_persisted_with_real_metrics():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            repo, snapshot, storage_path = _pinned_snapshot()
            try:
                with patch("services.council_orchestrator.WeightRepository", return_value=repo):
                    with SessionFactory.get_session() as session:
                        run = run_and_persist_backtest(
                            _tiny_data(),
                            session,
                            pinned_weight_snapshot_id=snapshot.id,
                            fee=0.001,
                            lookback=3,
                        )

                    with SessionFactory.get_session() as session:
                        row = BacktestRunRepository(session).get_by_id(run.id)
                        assert row is not None
                        symbols, git_sha, num_bars = set(row.symbols), row.git_sha, row.num_bars
                        metrics, equity_curve = dict(row.metrics), list(row.equity_curve)

                    assert symbols == {"BTCUSDT", "ETHUSDT"}
                    assert git_sha != "" and git_sha != "unknown"
                    assert num_bars == 8
                    assert metrics["max_drawdown"] <= 0.0
                    assert isinstance(metrics["sharpe_ratio"], float)
                    # VectorizedBacktestEngine.equity_curve has n_bars-1 entries; the
                    # orchestrator prepends the initial capital -> n_bars total.
                    # lookback only delays when signals turn nonzero, it doesn't shrink the array.
                    assert len(equity_curve) == num_bars
                    # equity curve must start at the assumed initial capital
                    assert equity_curve[0] == pytest.approx(100_000.0)
                    # max_drawdown must be independently reproducible from the persisted equity curve
                    from analytics.metrics.engine import MetricsEngine
                    assert MetricsEngine.max_drawdown(equity_curve) == pytest.approx(metrics["max_drawdown"])
            finally:
                shutil.rmtree(storage_path, ignore_errors=True)


def test_backtest_run_is_deterministic_across_two_persisted_runs():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            repo, snapshot, storage_path = _pinned_snapshot()
            try:
                with patch("services.council_orchestrator.WeightRepository", return_value=repo):
                    with SessionFactory.get_session() as session:
                        run_a = run_and_persist_backtest(
                            _tiny_data(), session, pinned_weight_snapshot_id=snapshot.id, lookback=3
                        )
                    with SessionFactory.get_session() as session:
                        run_b = run_and_persist_backtest(
                            _tiny_data(), session, pinned_weight_snapshot_id=snapshot.id, lookback=3
                        )

                assert run_a.id != run_b.id  # two distinct persisted rows
                assert run_a.total_pnl == pytest.approx(run_b.total_pnl)
                assert run_a.metrics == pytest.approx(run_b.metrics)
                assert run_a.equity_curve == pytest.approx(run_b.equity_curve)
            finally:
                shutil.rmtree(storage_path, ignore_errors=True)
