"""Walk-forward backtest motoru."""
from dataclasses import dataclass
from typing import List, Callable
from datetime import datetime, timedelta

@dataclass
class WalkForwardResult:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_return: float
    test_return: float

class WalkForwardEngine:
    def __init__(self, train_size: int = 200, test_size: int = 50, step: int = 50):
        self.train_size = train_size
        self.test_size = test_size
        self.step = step
    
    def run(self, prices: List[float], strategy: Callable[[List[float]], int]) -> List[WalkForwardResult]:
        results = []
        i = 0
        while i + self.train_size + self.test_size <= len(prices):
            train = prices[i:i + self.train_size]
            test = prices[i + self.train_size:i + self.train_size + self.test_size]
            signal = strategy(train)
            train_ret = sum(train[j+1] - train[j] for j in range(len(train)-1)) if signal > 0 else 0
            test_ret = sum(test[j+1] - test[j] for j in range(len(test)-1)) if signal > 0 else 0
            now = datetime.utcnow()
            results.append(WalkForwardResult(
                train_start=now - timedelta(days=len(prices)-i),
                train_end=now - timedelta(days=len(prices)-i-self.train_size),
                test_start=now - timedelta(days=len(prices)-i-self.train_size),
                test_end=now - timedelta(days=len(prices)-i-self.train_size-self.test_size),
                train_return=train_ret,
                test_return=test_ret
            ))
            i += self.step
        return results
