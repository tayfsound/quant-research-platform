"""End-to-end cognitive loop orchestrator — Phase 187 CognitiveEngine integration."""
from typing import Any
from market_data.ingestion.data_provider import get_ohlcv_provider, OHLCVProvider
from market_data.features.indicators import rsi, ema, macd
from simulator.fill_engine import FillEngine
from ml.training.replay_memory import ReplayMemory
from services.cognitive_engine import CognitiveEngine
from services.risk_gate import RiskGate
from services.risk_cycle_adapter import apply_gate_result
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
        self.risk_gate = RiskGate(
            max_position_size=max_position_size,
            max_drawdown=max_drawdown,
        )
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
        
        # Run cognitive engine
        ctx = self.engine.run(ctx)
        
        # Post-fusion risk gate
        ctx = self.risk_gate.evaluate(ctx)
        gated = apply_gate_result(ctx)
        
        market_price = data[-1].close
        if gated["approved"]:
            decision = {"direction": gated["direction"], "size": gated["size"]}
            result = self.fill_engine.simulate(decision, market_price)
            filled_price = result.filled_price
            fee = result.fee
        else:
            filled_price = market_price
            fee = 0.0
        
        if gated["approved"]:
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if filled_price > market_price else 0,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "risk_verdict": gated["risk_verdict"],
            })
        
        return {
            "direction": gated["direction"],
            "size": gated["size"],
            "filled_price": filled_price,
            "fee": fee,
            "memory_size": len(self.memory.memory),
            "risk_verdict": gated["risk_verdict"],
            "risk_reasons": gated["risk_reasons"],
            "action": gated["action"],
        }
