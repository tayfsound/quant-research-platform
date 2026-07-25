"""RL geri bildiriminden ağırlık adaptasyonu."""
from uuid import UUID


class WeightAdapter:
    def __init__(self, learning_rate: float = 0.01):
        self.weights: dict[UUID, float] = {}
        self.lr = learning_rate

    def update(self, agent_id: UUID, reward: float, direction_correct: bool):
        current = self.weights.get(agent_id, 1.0)
        delta = self.lr * reward * (1 if direction_correct else -1)
        self.weights[agent_id] = max(0.1, min(5.0, current + delta))
