"""End-to-end cognitive loop orchestrator — v1.1 trusted paper cycle."""
from typing import Any
from market_data.ingestion.data_provider import get_ohlcv_provider, OHLCVProvider
from market_data.features.indicators import rsi, ema, macd
from simulator.fill_engine import FillEngine
from ml.training.replay_memory import ReplayMemory
from services.cognitive_engine import CognitiveEngine
from services.forward_outcome import ForwardOutcome
from services.decision_recorder import DecisionRecorder
from config import get_settings
from contracts.context import CognitiveCycleContext

class CognitiveOrchestrator:
    def __init__(
        self,
        data_provider: OHLCVProvider | None = None,
        max_position_size: float = 1.0,
        max_drawdown: float = 0.15,
        current_drawdown: float = 0.0,
    ):
        self.engine = CognitiveEngine()
        self.fill_engine = FillEngine()
        self.memory = ReplayMemory(capacity=10000)
        self.forward = ForwardOutcome(bars_forward=10)
        self.recorder = DecisionRecorder()
        self.data_provider = data_provider or get_ohlcv_provider()
        self.max_position_size = max_position_size
        self.max_drawdown_limit = max_drawdown
        self.current_drawdown = current_drawdown

    def run_cycle(self, seed: int = 42, symbol: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        symbol = symbol or settings.DEFAULT_SYMBOL
        timeframe = settings.DEFAULT_TIMEFRAME
        
        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=100)
        if not data:
            return {"direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}
        
        # Build cognitive context
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.market.timeframe = timeframe
        ctx.market.features = {
            "rsi": rsi(data),
            "ema": ema(data),
            "macd": macd(data)["macd"],
        }
        ctx.market.raw_snapshot = {
            "close": data[-1].close,
            "volume": data[-1].volume,
            "high": data[-1].high,
            "low": data[-1].low,
        }
        
        # Run cognitive engine (council + meta + fusion + risk)
        ctx = self.engine.run(ctx)
        
        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0
        
        # Execution simulation
        if direction != "NEUTRAL" and size > 0:
            decision = {"direction": direction, "size": size}
            result = self.fill_engine.simulate(decision, market_price)
            filled_price = result.filled_price
            fee = result.fee
        else:
            filled_price = market_price
            fee = 0.0
        
        # Forward outcome
        outcome = self.forward.calculate(filled_price, direction, data)
        pnl = outcome["pnl"] - fee
        win = pnl > 0
        
        # Record decision (approve + reject)
        ctx.outcome = outcome
        self.recorder.record(ctx, [], None)
        
        # Memory (sadece risk-onaylı)
        if direction != "NEUTRAL" and size > 0:
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if win else 0,
                "pnl": pnl,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "direction": direction,
            })
        
        return {
            "direction": direction,
            "size": size,
            "filled_price": filled_price,
            "fee": fee,
            "pnl": pnl,
            "win": win,
            "memory_size": len(self.memory.memory),
            "risk_verdict": ctx.risk.evaluation.verdict if ctx.risk.evaluation else "unknown",
            "risk_reasons": [str(r) for r in ctx.risk.evaluation.reasons] if ctx.risk.evaluation else [],
            "action": ctx.decision.action.value if ctx.decision.action else "WAIT",
        }
