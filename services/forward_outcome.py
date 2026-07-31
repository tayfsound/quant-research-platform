"""N-bar forward outcome hesaplayici."""
from typing import List, Dict
from market_data.ingestion.ohlcv import OHLCV

class ForwardOutcome:
    def __init__(self, bars_forward: int = 10):
        self.bars_forward = bars_forward
    
    def calculate(self, entry_price: float, direction: str, data: List[OHLCV]) -> Dict:
        """N-bar forward outcome: entry = data[-(n+1)], exit = data[-1]."""
        n = self.bars_forward
        if len(data) < n + 1:
            return {
                "pnl": 0.0,
                "win": False,
                "entry_price": entry_price,
                "exit_price": entry_price,
                "bars": 0,
                "pending": True,
            }

        entry = data[-(n + 1)].close
        exit_px = data[-1].close

        if entry_price and entry_price > 0:
            entry = entry_price

        d = (direction or "").upper()
        if d == "LONG":
            pnl = exit_px - entry
        elif d == "SHORT":
            pnl = entry - exit_px
        else:
            pnl = 0.0

        return {
            "pnl": float(pnl),
            "win": pnl > 0,
            "entry_price": float(entry),
            "exit_price": float(exit_px),
            "bars": n,
            "pending": False,
        }