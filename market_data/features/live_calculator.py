"""Canlı tick verisinden teknik gösterge hesaplar."""
from collections import deque

from market_data.features.indicators import ema, macd, rsi


class LiveFeatureCalculator:
    def __init__(self, window: int = 50):
        self.prices = deque(maxlen=window)
        self.volumes = deque(maxlen=window)

    def update(self, price: float, volume: float) -> dict:
        self.prices.append(price)
        self.volumes.append(volume)
        if len(self.prices) < 14:
            return {}
        return {
            "rsi": rsi(list(self.prices)),
            "macd": macd(list(self.prices)).get("macd", 0.0),
            "ema_12": ema(list(self.prices), 12)[-1],
            "ema_26": ema(list(self.prices), 26)[-1],
            "price": price,
        }
