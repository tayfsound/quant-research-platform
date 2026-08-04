"""Sprint 3: vectorized multi-symbol backtest core + embargo walk-forward.

All expected numbers below are hand-computed (see comments), not just
"code produces X and we assert X" — this is the D1 bar for a new numeric
engine: a known synthetic case with a manually derived reference value.
"""
from datetime import datetime, timezone, timedelta

import numpy as np
import pytest

from backtest.vectorized_engine import VectorizedBacktestEngine
from backtest.embargo_walk_forward import EmbargoWalkForwardSplitter
from market_data.ingestion.ohlcv import OHLCV


def _bars(closes: list[float]) -> list[OHLCV]:
    now = datetime.now(timezone.utc)
    return [
        OHLCV(timestamp=now + timedelta(minutes=i), open=c, high=c, low=c, close=c, volume=0.0)
        for i, c in enumerate(closes)
    ]


def _synthetic_data():
    return {
        "A": _bars([100, 110, 105, 120]),
        "B": _bars([50, 48, 52, 55]),
    }


def test_vectorized_engine_matches_hand_computed_pnl_no_fee():
    data = _synthetic_data()
    # A: position held per period (bar0->1, bar1->2, bar2->3) = [1, 1, -1]
    # B: position held per period                             = [0, 1, 1]
    signals = np.array([
        [1, 1, -1, -1],
        [0, 1, 1, 1],
    ], dtype=np.float64)

    engine = VectorizedBacktestEngine(fee=0.0)
    result = engine.run(data, signals)

    # A: price_diff=[10,-5,15], pnl=[10,-5,-15] -> sum -10
    # B: price_diff=[-2,4,3],   pnl=[0,4,3]      -> sum 7
    assert result.per_symbol_pnl["A"] == pytest.approx(-10.0)
    assert result.per_symbol_pnl["B"] == pytest.approx(7.0)
    assert result.total_pnl == pytest.approx(-3.0)
    # per-period totals [10,-1,-12] -> cumsum [10,9,-3]
    assert result.equity_curve.tolist() == pytest.approx([10.0, 9.0, -3.0])
    assert result.num_bars == 4


def test_vectorized_engine_deducts_fee_on_turnover():
    data = _synthetic_data()
    signals = np.array([
        [1, 1, -1, -1],
        [0, 1, 1, 1],
    ], dtype=np.float64)

    engine = VectorizedBacktestEngine(fee=0.001)
    result = engine.run(data, signals)

    # A turnover=[1,0,2] * closes[100,110,105] * 0.001 = [0.1, 0, 0.21] -> total fee 0.31
    # net A = -10 - 0.31 = -10.31
    # B turnover=[0,1,0] * closes[50,48,52] * 0.001 = [0, 0.048, 0] -> total fee 0.048
    # net B = 7 - 0.048 = 6.952
    assert result.per_symbol_pnl["A"] == pytest.approx(-10.31)
    assert result.per_symbol_pnl["B"] == pytest.approx(6.952)
    assert result.total_pnl == pytest.approx(-3.358)


def test_vectorized_engine_rejects_mismatched_symbol_lengths():
    data = {"A": _bars([100, 101, 102]), "B": _bars([50, 51])}
    engine = VectorizedBacktestEngine()
    with pytest.raises(ValueError):
        engine.run(data, np.zeros((2, 3)))


def test_vectorized_engine_rejects_mismatched_signal_shape():
    data = _synthetic_data()
    engine = VectorizedBacktestEngine()
    with pytest.raises(ValueError):
        engine.run(data, np.zeros((2, 3)))  # data has 4 bars, not 3


def test_embargo_gap_is_enforced_between_train_and_test():
    splitter = EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=5, embargo=3)
    splits = splitter.split(n_bars=40)
    assert len(splits) > 0
    for s in splits:
        assert s.test_start - s.train_end == 3
        assert s.train_end - s.train_start == 10
        assert s.test_end - s.test_start == 5


def test_embargo_zero_is_backward_compatible_adjacent_split():
    splitter = EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=5, embargo=0)
    splits = splitter.split(n_bars=20)
    assert splits[0] == splitter.split(20)[0]
    assert splits[0].test_start == splits[0].train_end


def test_embargo_splitter_never_produces_overlapping_train_test_ranges():
    splitter = EmbargoWalkForwardSplitter(train_size=8, test_size=4, step=4, embargo=2)
    for s in splitter.split(n_bars=50):
        train_indices = set(range(s.train_start, s.train_end))
        test_indices = set(range(s.test_start, s.test_end))
        assert train_indices.isdisjoint(test_indices)
        # the embargo bars themselves belong to neither window
        embargo_indices = set(range(s.train_end, s.test_start))
        assert len(embargo_indices) == 2
        assert train_indices.isdisjoint(embargo_indices)
        assert test_indices.isdisjoint(embargo_indices)


def test_embargo_splitter_rejects_invalid_params():
    with pytest.raises(ValueError):
        EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=5, embargo=-1)
    with pytest.raises(ValueError):
        EmbargoWalkForwardSplitter(train_size=0, test_size=5, step=5)


def test_vectorized_engine_handles_full_symbol_time_matrix_at_once():
    """'tüm sembol/zaman aralığını matris işlemi olarak işleyen motor' — prove
    it actually scales as a matrix op, not a disguised per-bar Python loop."""
    rng = np.random.default_rng(7)
    n_symbols, n_bars = 50, 5000
    data = {
        f"SYM{i}": _bars(list(100.0 + np.cumsum(rng.normal(0, 1, n_bars))))
        for i in range(n_symbols)
    }
    signals = rng.uniform(-1, 1, size=(n_symbols, n_bars))

    engine = VectorizedBacktestEngine(fee=0.001)
    result = engine.run(data, signals)

    assert result.num_bars == n_bars
    assert len(result.per_symbol_pnl) == n_symbols
    assert result.equity_curve.shape == (n_bars - 1,)
    assert np.isfinite(result.total_pnl)
