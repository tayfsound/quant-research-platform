"""Deterministik mock OHLCV uretici."""
import random
from datetime import datetime, timedelta
from market_data.ingestion.ohlcv import OHLCV

class MockOHLCVAdapter:
    def __init__(self, seed: int = 42, base_price: float = 50000.0):
        self.rng = random.Random(seed)
        self.base_price = base_price

    def generate(self, n: int = 100):
        data = []
        price = self.base_price
        now = datetime.utcnow()
        for i in range(n):
            change = self.rng.gauss(0, price * 0.02)
            open_p = price
            close_p = price + change
            high_p = max(open_p, close_p) + abs(self.rng.gauss(0, price * 0.01))
            low_p = min(open_p, close_p) - abs(self.rng.gauss(0, price * 0.01))
            vol = abs(self.rng.gauss(0, 1000)) + 500
            data.append(OHLCV(
                timestamp=now - timedelta(minutes=n-i),
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
                volume=round(vol, 2)
            ))
            price = close_p
        return data
