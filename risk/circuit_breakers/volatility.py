"""Volatility-based circuit breaker."""
from typing import List

class VolatilityCircuitBreaker:
    def __init__(self, threshold: float = 0.05, lookback: int = 20):
        self.threshold = threshold
        self.lookback = lookback
        self.history: List[float] = []
        self.tripped: bool = False
    
    def check(self, price: float) -> bool:
        self.history.append(price)
        if len(self.history) > self.lookback:
            self.history.pop(0)
        if len(self.history) < 2:
            return True
        returns = [abs(self.history[i] - self.history[i-1]) / self.history[i-1] for i in range(1, len(self.history))]
        avg_vol = sum(returns) / len(returns)
        if avg_vol > self.threshold:
            self.tripped = True
            return False
        return True
    
    def reset(self):
        self.tripped = False
        self.history = []
