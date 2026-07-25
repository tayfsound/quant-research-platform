"""Meta-AI ağırlıklı oylama sistemi."""
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class AgentVote:
    agent_id: UUID
    direction: int  # -1, 0, 1
    confidence: float

@dataclass
class EnsembleDecision:
    direction: int
    confidence: float
    votes: list[AgentVote] = field(default_factory=list)

class WeightedVoting:
    def __init__(self):
        self._weights: dict[UUID, float] = {}

    def set_weight(self, agent_id: UUID, weight: float):
        self._weights[agent_id] = weight

    def decide(self, votes: list[AgentVote]) -> EnsembleDecision:
        total = 0.0
        weighted_sum = 0.0
        for v in votes:
            w = self._weights.get(v.agent_id, 1.0)
            weighted_sum += v.direction * v.confidence * w
            total += abs(v.confidence * w)
        if total == 0:
            return EnsembleDecision(direction=0, confidence=0.0, votes=votes)
        score = weighted_sum / total
        direction = 1 if score > 0.1 else (-1 if score < -0.1 else 0)
        return EnsembleDecision(direction=direction, confidence=abs(score), votes=votes)
