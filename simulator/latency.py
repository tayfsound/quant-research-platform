"""Gecikme modeli."""
import random


class LatencyModel:
    def __init__(self, base_ms: int = 50, jitter_ms: int = 20):
        self.base_ms = base_ms
        self.jitter_ms = jitter_ms

    def get_latency_ms(self) -> int:
        return self.base_ms + random.randint(0, self.jitter_ms)
