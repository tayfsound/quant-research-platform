"""Memory modelleri — Episode embedding alanı eklendi."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MemoryType(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"

class WorkingMemory(BaseModel):
    cycle_id: UUID = Field(default_factory=uuid4)
    observations: list[dict] = Field(default_factory=list)
    bindings: list[dict] = Field(default_factory=list)
    max_items: int = 10

    def add_observation(self, obs: dict):
        self.observations.append(obs)
        if len(self.observations) > self.max_items:
            self.observations = self.observations[-self.max_items:]

    def clear(self):
        self.observations.clear()
        self.bindings.clear()

class EpisodicMemory(BaseModel):
    episodes: list["Episode"] = Field(default_factory=list)

    def add_episode(self, episode: "Episode"):
        self.episodes.append(episode)

    def sample(self, n: int = 10, seed: int | None = None) -> list["Episode"]:
        import random
        rng = random.Random(seed)
        return rng.sample(self.episodes, min(n, len(self.episodes))) if self.episodes else []

class Episode(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    cycle_id: UUID | None = None
    symbol: str = ""
    observation: dict = Field(default_factory=dict)
    binding_expression: str = ""
    decision: str = ""
    outcome: dict | None = None
    lesson: str = ""
    embedding: list[float] | None = None

class SemanticMemory(BaseModel):
    consolidated_beliefs: list[dict] = Field(default_factory=list)
    total_episodes: int = 0
    last_consolidation: datetime | None = None

    def add_belief(self, expression: str, confidence: float):
        self.consolidated_beliefs.append({
            "expression": expression,
            "confidence": confidence,
            "evidence_count": 1,
        })

    def consolidate(self, episodic: EpisodicMemory, threshold: int = 10):
        if len(episodic.episodes) < threshold:
            return
        recent = episodic.episodes[-threshold:]
        wins = sum(1 for e in recent if e.outcome and e.outcome.get("pnl", 0) > 0)
        win_rate = wins / threshold
        for belief in self.consolidated_beliefs:
            if belief.get("expression") in [e.binding_expression for e in recent]:
                belief["confidence"] = (belief.get("confidence", 0.5) + win_rate) / 2
                belief["evidence_count"] = belief.get("evidence_count", 0) + threshold
        self.total_episodes += threshold
        self.last_consolidation = datetime.now()
