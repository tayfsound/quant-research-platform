"""Sprint 5: Replay <-> Backtest integration — same CognitiveEngine.run(),
different scale. Also the weight-snapshot-pinning determinism fix."""
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backtest.cognitive_backtest_runner import run_cognitive_backtest
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


def test_backtest_runner_actually_invokes_cognitive_engine_run():
    """Prove this calls the real single-decision function, not a parallel
    simplified decision path — the exact thing Sprint 5's gate asks for."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.cognitive_engine import CognitiveEngine

            engine = CognitiveEngine()
            data = _tiny_data()

            with patch.object(engine, "run", wraps=engine.run) as spy_run:
                result = run_cognitive_backtest(data, lookback=3, engine=engine)

                # 2 symbols * (8 bars - 3 lookback) = 10 real engine.run() calls
                assert spy_run.call_count == 10

            assert set(result.symbols) == {"BTCUSDT", "ETHUSDT"}
            assert result.num_bars == 8


def test_backtest_is_deterministic_with_a_pinned_weight_snapshot():
    """Same pinned snapshot -> identical result on repeated runs. Without
    pinning, this would be flaky whenever a weight snapshot gets written
    between the two runs (get_latest() would pick up a different snapshot)."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from contracts.agent_weight_snapshot import AgentWeightSnapshot
            from services.weight_repository import WeightRepository

            storage_path = "test_backtest_weight_history"
            shutil.rmtree(storage_path, ignore_errors=True)
            repo = WeightRepository(storage_path=storage_path)
            snapshot = repo.save(
                AgentWeightSnapshot(weights={"technical": 1.0, "macro": 1.0}).finalize()
            )

            with patch("services.council_orchestrator.WeightRepository", return_value=repo):
                data = _tiny_data()
                result_a = run_cognitive_backtest(
                    data, pinned_weight_snapshot_id=snapshot.id, lookback=3
                )
                result_b = run_cognitive_backtest(
                    data, pinned_weight_snapshot_id=snapshot.id, lookback=3
                )

            assert result_a.per_symbol_pnl == pytest.approx(result_b.per_symbol_pnl)
            assert result_a.total_pnl == pytest.approx(result_b.total_pnl)
            assert result_a.equity_curve.tolist() == pytest.approx(result_b.equity_curve.tolist())

            shutil.rmtree(storage_path, ignore_errors=True)


def test_backtest_rejects_symbols_with_mismatched_bar_counts():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            data = {"A": _bars([100, 101, 102]), "B": _bars([50, 51])}
            with pytest.raises(ValueError):
                run_cognitive_backtest(data, lookback=1)
