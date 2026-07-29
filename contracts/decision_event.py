"""Decision event contracts."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    EXPERIMENT = "experiment"
    PAPER = "paper"
    LIVE = "live"


class DecisionEvent(BaseModel):
    """A recorded decision with full provenance."""
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = ""
    proposed_direction: Optional[str] = None
    final_action: Optional[str] = None
    final_size: float = 0.0
    confidence: float = 0.0
    agent_opinions: list[dict] = Field(default_factory=list)
    risk_evaluation: Optional[dict] = None
    market_snapshot: Optional[dict] = None
    belief_state: Optional[dict] = None
    outcome: Optional[dict] = None
    weight_snapshot_id: Optional[UUID] = None
    belief_snapshot_id: Optional[UUID] = None
