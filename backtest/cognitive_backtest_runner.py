"""Sprint 5: Replay <-> Backtest integration — runs the SAME
CognitiveEngine.run() used by services/replay_engine.py's single-decision
replay, once per bar per symbol, and feeds the resulting decisions into
VectorizedBacktestEngine. This is deliberately NOT a second, simplified
decision function for backtesting — that would recreate the exact
CognitiveEngine/Orchestrator "two brains" problem this project already
tracks as a known debt, just one layer down.

Determinism note: no risk-limit provisioning exists anywhere in production
(see AI_MEMORY_SYSTEM/CURRENT_STATE.md known gap on this) — every real
usage that reaches RiskEngine.execute() today is a test double. This module
uses the same minimal shape (.value / .verify(secret)) rather than inventing
a fourth parallel risk-limit representation.
"""
from dataclasses import dataclass

import numpy as np

from contracts.context import CognitiveCycleContext
from market_data.ingestion.ohlcv import OHLCV
from services.cognitive_engine import CognitiveEngine
from backtest.vectorized_engine import BacktestResult, VectorizedBacktestEngine

DIRECTION_TO_SIGN = {"LONG": 1.0, "SHORT": -1.0, "WAIT": 0.0, "NEUTRAL": 0.0}


@dataclass
class _UnlimitedPositionLimit:
    value: float = 1.0

    def verify(self, secret: str) -> bool:
        return True


def run_cognitive_backtest(
    data: dict[str, list[OHLCV]],
    pinned_weight_snapshot_id=None,
    fee: float = 0.001,
    lookback: int = 3,
    engine: CognitiveEngine | None = None,
) -> BacktestResult:
    """
    data: {symbol: [OHLCV, ...]} — same bar count per symbol.
    pinned_weight_snapshot_id: fixed weight snapshot for the whole run — a
        real backtest must NOT use "latest" weights (see CognitiveEngine's
        pinned_weight_snapshot_id docstring), otherwise a decision simulated
        for bar 10 could use weights the system only learned from bar 500
        onward — a lookahead leak.
    lookback: bars of history handed to the engine per decision.
    engine: inject a pre-built CognitiveEngine (e.g. for reusing one across
        many backtest calls in a test); otherwise one is constructed with
        pinned_weight_snapshot_id.
    """
    engine = engine or CognitiveEngine(pinned_weight_snapshot_id=pinned_weight_snapshot_id)

    symbols = list(data.keys())
    lengths = {len(v) for v in data.values()}
    if len(lengths) != 1:
        raise ValueError(f"all symbols must have the same number of bars, got {lengths}")
    n_bars = lengths.pop()

    signals = np.zeros((len(symbols), n_bars))

    for si, symbol in enumerate(symbols):
        bars = data[symbol]
        for t in range(lookback, n_bars):
            window = bars[t - lookback: t + 1]

            ctx = CognitiveCycleContext()
            ctx.market.symbol = symbol
            # Deliberately NOT setting ctx.market.features here: MemoryStage ->
            # DecisionContextBuilder.enrich() only calls the embedding-based
            # SemanticSearch path when features is non-empty, and that path
            # has zero test coverage anywhere in this repo and breaks under
            # the standard transformers.* mock pattern (see CURRENT_STATE
            # known gap). Every other passing full-cycle test avoids it the
            # same way. A real backtest wiring features in is future work.
            ctx.decision.proposed_direction = "LONG" if window[-1].close >= window[0].close else "SHORT"
            ctx.decision.proposed_size = 1.0
            ctx.decision.confidence = 0.5
            ctx.risk.current_drawdown = 0.0
            ctx.risk.limits = {"max_position_size": _UnlimitedPositionLimit()}

            result_ctx = engine.run(ctx, persist=False)

            direction = result_ctx.decision.proposed_direction or "WAIT"
            sign = DIRECTION_TO_SIGN.get(direction, 0.0)
            size = getattr(result_ctx.decision, "final_size", 0.0) or 0.0
            signals[si, t] = sign * (size if size else 1.0) if sign else 0.0

    return VectorizedBacktestEngine(fee=fee).run(data, signals)
