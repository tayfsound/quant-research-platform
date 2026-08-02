"""Weight approval contract — Faz 160."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class WeightApproval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    proposed_weights: dict = Field(default_factory=dict)
    previous_weights: dict = Field(default_factory=dict)
    max_delta: float = 0.10
    status: str = "pending"  # pending | approved | rejected
    approved_by: str = ""    # human or system
