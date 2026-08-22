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
    # Faz 268b — Regime-Aware Learning: None = global (rejimden bağımsız)
    # öneri, aksi halde "trend_volatility" formatında (bkz. PositionCloser.
    # _record_agent_learning) hangi piyasa rejimi için önerildiği.
    regime: str | None = None
    status: str = "pending"  # pending | approved | rejected
    approved_by: str = ""    # human or system
    expires_at: datetime | None = None  # TTL: None = no expiry
    decided_at: datetime | None = None  # set on approve/reject, used for latency metrics
