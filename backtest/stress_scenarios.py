"""Stres senaryoları."""
from typing import List, Dict, Callable
import random

class StressEngine:
    SCENARIOS: Dict[str, Callable[[List[float]], List[float]]] = {
        "flash_crash": lambda p: [v * (0.7 if i > len(p)//2 else 1.0) for i, v in enumerate(p)],
        "rally": lambda p: [v * (1.3 if i > len(p)//2 else 1.0) for i, v in enumerate(p)],
        "chop": lambda p: [v + random.gauss(0, v*0.05) for v in p],
    }
    
    def apply(self, prices: List[float], scenario: str) -> List[float]:
        if scenario not in self.SCENARIOS:
            return prices
        return self.SCENARIOS[scenario](prices)
    
    def run_all(self, prices: List[float]) -> Dict[str, List[float]]:
        return {name: fn(prices) for name, fn in self.SCENARIOS.items()}
