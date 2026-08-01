"""Pending outcome tracker — Faz 162 önkoşulu."""
from typing import List, Dict
from datetime import datetime


class PendingOutcomeTracker:
    """Tracks pending outcomes until sufficient bars arrive."""

    def __init__(self):
        self.pending: List[Dict] = []

    def add(self, decision_id: str, entry_price: float, direction: str, required_bars: int, timestamp: datetime) -> None:
        self.pending.append({
            "decision_id": decision_id,
            "entry_price": entry_price,
            "direction": direction,
            "required_bars": required_bars,
            "timestamp": timestamp,
        })

    def check_and_finalize(self, data_provider, symbol: str, timeframe: str) -> List[Dict]:
        """Stub — real implementation needs data provider + scheduler integration."""
        finalized = []
        for item in list(self.pending):
            data = data_provider.get_ohlcv(symbol, timeframe, limit=item["required_bars"] + 1)
            if len(data) >= item["required_bars"] + 1:
                from services.forward_outcome import ForwardOutcome
                fo = ForwardOutcome(bars_forward=item["required_bars"])
                result = fo.calculate(item["entry_price"], item["direction"], data)
                if not result["pending"]:
                    finalized.append({"decision_id": item["decision_id"], "result": result})
                    self.pending.remove(item)
        return finalized

    def count(self) -> int:
        return len(self.pending)
