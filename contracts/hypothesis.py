"""Hypothesis — gözlemden türetilen test edilebilir önerme."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    TESTING = "testing"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"

class Hypothesis(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    statement: str                     # "High volatility is negatively correlated with win rate"
    observation_ids: list[UUID] = Field(default_factory=list)
    belief_ids: list[UUID] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    effect_size: float | None = None   # Cohen's d veya benzeri
    p_value: float | None = None
    sample_size: int = 0
    confidence_interval: tuple[float, float] | None = None
    proposed_experiment: str = ""      # "Reduce position size by 30% when ATR > 3%"
    priority_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
