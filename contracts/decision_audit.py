"""Decision Audit — immutable karar kaydı."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ModelOutput(BaseModel):
    agent_id: UUID
    direction: str
    confidence: float
    latency_ms: int = 0
    token_usage: int = 0
    model_version: str = ""

class DecisionAuditRecord(BaseModel):
    trade_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    symbol: str
    market_snapshot_ref: UUID
    feature_vector_ref: UUID
    model_outputs: list[ModelOutput] = Field(default_factory=list)
    risk_limits_applied: dict[str, float] = Field(default_factory=dict)
    llm_explanation: dict = Field(default_factory=dict)
    llm_risk_factor: float = 1.0
    prompt_hash: str = ""
    prompt_version: str = ""
    risk_gate_verdict: str = ""
    final_direction: str = ""
    final_size: float = 0.0
    outcome: dict | None = None
    system_version: str = ""
    schema_version: int = 3
