"""Basit slippage modeli."""
import random


class SlippageModel:
    def __init__(self, base_bps: float = 5.0, volatility_factor: float = 1.0):
        self.base_bps = base_bps
        self.volatility_factor = volatility_factor

    def apply(self, price: float, side: str, size: float) -> float:
        rng = random.Random(hash(f"{price}{side}{size}"))
        slip_bps = self.base_bps * self.volatility_factor * (0.5 + rng.random())
        slip = price * (slip_bps / 10000)
        return price + slip if side == "BUY" else price - slip
