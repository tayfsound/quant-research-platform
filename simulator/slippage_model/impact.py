"""Slippage ve piyasa etkisi modeli."""
import random


class SlippageModel:
    def __init__(self, base_slippage: float = 0.0001):
        self.base_slippage = base_slippage

    def compute(self, size: float, volume: float) -> float:
        """Hacme göre artan slippage."""
        impact = self.base_slippage * (1 + size / max(volume, 1))
        noise = random.uniform(0, self.base_slippage)
        return impact + noise
