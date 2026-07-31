"""N-bar forward outcome hesaplayici."""
from typing import List, Dict
from market_data.ingestion.ohlcv import OHLCV

class ForwardOutcome:
    def __init__(self, bars_forward: int = 10):
        self.bars_forward = bars_forward
    
    def calculate(self, entry_price: float, direction: str, data: List[OHLCV], fee: float = 0.0) -> Dict:
        """N bar sonraki fiyata gore PnL hesapla."""
        if len(data) < 2:
            return {"pnl": 0.0, "win": False, "exit_price": entry_price, "bars": 0}

        # FIX: bars_forward kadar ileri git (eskisi data[-1].close idi)
        exit_idx = min(self.bars_forward, len(data) - 1)
        exit_price = data[exit_idx].close

        if direction == "LONG":
            pnl = exit_price - entry_price
        elif direction == "SHORT":
            pnl = entry_price - exit_price
        else:
            pnl = 0.0

        net_pnl = pnl - fee

        return {
            "pnl": net_pnl,
            "win": net_pnl > 0,
            "exit_price": exit_price,
            "bars": exit_idx,
        }