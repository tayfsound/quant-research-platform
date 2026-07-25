"""Decision Event — zenginleştirilmiş: latency, hash, debate trace."""
from datetime import datetime, UTC
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class DecisionEvent(BaseModel):
    schema_version: str = "cognitive-core-v1"

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    symbol: str = ""
    market_snapshot: dict = Field(default_factory=dict)

    agent_opinions: list[dict] = Field(default_factory=list)

    belief_state: dict = Field(default_factory=dict)

    cognitive_audit: dict | None = None

    # NEW
    debate_trace: dict | None = None

    risk_evaluation: dict = Field(default_factory=dict)

    proposed_direction: str = ""
    original_direction: str = ""

    final_action: str = ""
    final_reason: str = ""

    final_size: float = 0.0
    confidence: float = 0.0

    risk_adjusted: bool = False
    rejection_reason: str | None = None

    outcome: dict | None = None

    engine_version: str = "1.0.0"
    weight_snapshot_id: UUID | None = None
    git_commit: str = ""

    decision_latency_ms: float = 0.0

    feature_hash: str = ""
    belief_hash: str = ""

    data_sources: list[str] = Field(default_factory=list)
