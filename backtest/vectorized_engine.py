"""Vectorized multi-symbol backtest core — numpy matrix ops, no per-bar Python
loop. Shared foundation for Backtest and (later) Portfolio Engine risk calcs,
per the "no duplicate logic" rule: both need the same "process a whole
symbol/time matrix at once" primitive.
"""
from dataclasses import dataclass

import numpy as np

from market_data.ingestion.ohlcv import OHLCV


@dataclass
class BacktestResult:
    symbols: list[str]
    equity_curve: np.ndarray  # cumulative net pnl over time, shape [n_bars - 1]
    per_symbol_pnl: dict[str, float]
    total_pnl: float
    num_bars: int


def _to_close_matrix(data: dict[str, list[OHLCV]]) -> tuple[list[str], np.ndarray]:
    symbols = list(data.keys())
    lengths = {len(v) for v in data.values()}
    if len(lengths) != 1:
        raise ValueError(f"All symbols must have the same number of bars, got {lengths}")
    closes = np.array([[bar.close for bar in data[sym]] for sym in symbols], dtype=np.float64)
    return symbols, closes


class VectorizedBacktestEngine:
    """Runs a signal matrix against a price matrix for ALL symbols/timesteps
    in one set of numpy operations — no Python loop over bars or symbols."""

    def __init__(self, fee: float = 0.001):
        self.fee = fee

    def run(self, data: dict[str, list[OHLCV]], signals: np.ndarray) -> BacktestResult:
        """
        data: {symbol: [OHLCV, ...]} — every symbol must have the same number of bars.
        signals: [n_symbols, n_bars] position size per symbol/bar, typically in
                 [-1, 1]. signals[:, t] is the position entered at bar t's close
                 and held until bar t+1's close (so the last column has no
                 realized pnl and only matters for the final turnover/fee calc).
        """
        symbols, closes = _to_close_matrix(data)
        n_symbols, n_bars = closes.shape
        if signals.shape != closes.shape:
            raise ValueError(f"signals shape {signals.shape} must match price shape {closes.shape}")
        if n_bars < 2:
            raise ValueError("need at least 2 bars to compute any pnl")

        price_diff = np.diff(closes, axis=1)  # [n_symbols, n_bars-1]
        position = signals[:, :-1]  # position held over each of the n_bars-1 periods
        gross_pnl = position * price_diff

        prev_position = np.concatenate(
            [np.zeros((n_symbols, 1)), position[:, :-1]], axis=1
        )
        turnover = np.abs(position - prev_position)
        fee_cost = turnover * closes[:, :-1] * self.fee

        net_pnl = gross_pnl - fee_cost

        per_symbol_pnl = {sym: float(net_pnl[i].sum()) for i, sym in enumerate(symbols)}
        equity_curve = np.cumsum(net_pnl.sum(axis=0))

        return BacktestResult(
            symbols=symbols,
            equity_curve=equity_curve,
            per_symbol_pnl=per_symbol_pnl,
            total_pnl=float(net_pnl.sum()),
            num_bars=n_bars,
        )
