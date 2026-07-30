"""End-to-end cognitive loop orchestrator."""
from typing import Dict, Any
from market_data.ingestion.mock_adapter import MockOHLCVAdapter
from market_data.features.indicators import rsi, ema, macd
from simulator.fill_engine import FillEngine
from ml.training.replay_memory import ReplayMemory

class CognitiveOrchestrator:
    def __init__(self):
        self.fill_engine = FillEngine()
        self.memory = ReplayMemory(capacity=10000)
    
    def run_cycle(self, seed: int = 42) -> Dict[str, Any]:
        adapter = MockOHLCVAdapter(seed=seed)
        data = adapter.generate(100)
        features = {
            "rsi": rsi(data),
            "ema": ema(data),
            "macd": macd(data)["macd"]
        }
        direction = "LONG" if features["rsi"] < 40 else "SHORT" if features["rsi"] > 60 else "NEUTRAL"
        decision = {"direction": direction, "size": 0.5}
        result = self.fill_engine.simulate(decision, data[-1].close)
        
        if direction != "NEUTRAL":
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": features,
                "label": 1 if result.filled_price > data[-1].close else 0,
                "quality_score": 0.8,
                "timestamp": "2026-07-30T00:00:00"
            })
        
        return {
            "direction": direction,
            "filled_price": result.filled_price,
            "fee": result.fee,
            "memory_size": len(self.memory.memory)
        }
