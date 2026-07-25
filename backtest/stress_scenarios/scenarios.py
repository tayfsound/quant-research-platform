"""Stres test senaryoları."""
import numpy as np


class StressScenarios:
    @staticmethod
    def flash_crash(price: float, drop_pct: float = 0.3) -> float:
        return price * (1 - drop_pct)

    @staticmethod
    def volatility_spike(returns: list[float], factor: float = 5.0) -> list[float]:
        return [r * factor for r in returns]

    @staticmethod
    def black_swan(prices: list[float], drop_pct: float = 0.5, recovery_days: int = 100) -> list[float]:
        result = prices.copy()
        crash_idx = len(result) // 2
        result[crash_idx] *= (1 - drop_pct)
        for i in range(crash_idx + 1, min(crash_idx + recovery_days, len(result))):
            result[i] = result[i - 1] * 1.001
        return result

    @staticmethod
    def regime_test(prices: list[float], regime: str) -> list[float]:
        if regime == "bull":
            return [p * (1 + 0.001 * i) for i, p in enumerate(prices)]
        elif regime == "bear":
            return [p * (1 - 0.001 * i) for i, p in enumerate(prices)]
        elif regime == "sideways":
            return [p * (1 + 0.0001 * np.sin(i * 0.1)) for i, p in enumerate(prices)]
        return prices
