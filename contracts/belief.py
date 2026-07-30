"""Belief System v3 — FROZEN. Epistemik motor, cluster balance, log crowding, evidence paths."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Belief(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    direction: str = ""
    strength: float = 0.0
    uncertainty: float = 1.0
    entropy: float = 0.0
    information_clusters: int = 0
    total_opinions: int = 0
    cluster_disagreement: float = 0.0
    cluster_balance: float = 0.0
    crowding_penalty: float = 0.0
    cluster_weights: dict[str, float] = Field(default_factory=dict)
    supporting_opinions: list[str] = Field(default_factory=list)
    opposing_opinions: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    age_seconds: int = 0
    revision_count: int = 0
    stability: float = 0.5
