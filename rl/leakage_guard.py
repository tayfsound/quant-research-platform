"""RL sızıntı ve ödül hackleme test altyapısı."""

import numpy as np


class LeakageGuard:
    @staticmethod
    def purge_embargo_split(data: list, embargo_hours: int = 48) -> tuple[list, list]:
        """Embaro aralığı ile train/test ayır."""
        split_idx = int(len(data) * 0.8)
        return data[:split_idx - embargo_hours], data[split_idx:]

    @staticmethod
    def synthetic_regime_shock(returns: list[float], shock_factor: float = 3.0) -> list[float]:
        """Sentetik rejim şoku enjekte et."""
        shocked = returns.copy()
        for i in range(len(shocked) // 2, len(shocked)):
            shocked[i] *= shock_factor
        return shocked

    @staticmethod
    def reward_label_shuffle_test(rewards: list[float], agent_performance: float) -> bool:
        """Ödül etiketi karıştırma testi."""
        shuffled = np.random.permutation(rewards)
        return abs(np.mean(shuffled) - agent_performance) < 0.1

    @staticmethod
    def chronological_oos_shock(metrics: list[float], threshold: float = 0.3) -> bool:
        """Kronolojik OOS şok penceresi testi."""
        if len(metrics) < 10:
            return True
        recent = metrics[-5:]
        older = metrics[-10:-5]
        degradation = (np.mean(older) - np.mean(recent)) / max(np.mean(older), 1e-8)
        return degradation > threshold
