"""Simüle fill motoru."""
from dataclasses import dataclass
from typing import Optional
from simulator.fee_engine import FeeEngine
from simulator.slippage_model import SlippageModel

@dataclass
class FillResult:
    filled_price: float
    fee: float
    pnl: Optional[float]

class FillEngine:
    def __init__(self):
        self.fee = FeeEngine()
        self.slippage = SlippageModel()
    
    def simulate(self, decision: dict, market_price: float) -> FillResult:
        side = decision.get("direction", "NEUTRAL")
        if side == "NEUTRAL":
            return FillResult(filled_price=market_price, fee=0.0, pnl=0.0)
        
        size = decision.get("size", 1.0)
        filled = self.slippage.apply(market_price, side, size)
        notional = filled * size
        fee = self.fee.calculate(notional)
        return FillResult(filled_price=filled, fee=fee, pnl=None)
