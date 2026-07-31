"""N-bar forward outcome hesaplayici."""
from typing import List, Dict
from market_data.ingestion.ohlcv import OHLCV

class ForwardOutcome:
    def __init__(self, bars_forward: int = 10):
        self.bars_forward = bars_forward
    
    def calculate(self, entry_price: float, direction: str, data: List[OHLCV]) -> Dict:
        """N bar sonraki fiyata gore PnL hesapla."""
        if len(data) < self.bars_forward + 1:
            return {"pnl": 0.0, "win": False, "exit_price": entry_price, "bars": 0}
        
        exit_price = data[-1].close  # Simulated: en son bar
        if direction == "LONG":
            pnl = exit_price - entry_price
        elif direction == "SHORT":
            pnl = entry_price - exit_price
        else:
            pnl = 0.0
        
        return {
            "pnl": pnl,
            "win": pnl > 0,
            "exit_price": exit_price,
            "bars": len(data),
        }
