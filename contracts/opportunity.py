"""Opportunity Cost — exit_price eklendi."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OpportunityCost(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str = ""
    decision: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = 0.0
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    holding_period_minutes: int = 0
    missed_r_multiple: float = 0.0
    wait_was_correct: bool = True
    confidence_at_decision: float = 0.0
