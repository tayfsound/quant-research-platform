"""Event‑sourced historical replay engine."""
from collections.abc import Callable


class HistoricalReplay:
    def __init__(self, data: list[dict]):
        self.data = sorted(data, key=lambda x: x["timestamp"])

    def run(self, on_candle: Callable[[dict], dict | None]) -> list[dict]:
        results = []
        for candle in self.data:
            decision = on_candle(candle)
            if decision:
                results.append(decision)
        return results
