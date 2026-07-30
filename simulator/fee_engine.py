"""Sabit oranlı fee motoru."""
from dataclasses import dataclass

@dataclass
class FeeConfig:
    maker_rate: float = 0.0002  # %0.02
    taker_rate: float = 0.0005  # %0.05

class FeeEngine:
    def __init__(self, config: FeeConfig = None):
        self.config = config or FeeConfig()
    
    def calculate(self, notional: float, is_maker: bool = False) -> float:
        rate = self.config.maker_rate if is_maker else self.config.taker_rate
        return notional * rate
