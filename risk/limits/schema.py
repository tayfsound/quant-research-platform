"""Risk limit şeması ve imzalı yapılandırma."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class LimitType(StrEnum):
    MAX_POSITION_SIZE = "max_position_size"
    MAX_LEVERAGE = "max_leverage"
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_EXPOSURE = "max_exposure"
    CIRCUIT_BREAKER = "circuit_breaker"

class RiskLimit(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scope: str = "global"
    limit_type: LimitType
    value: float
    signed_hash: str
    effective_at: datetime
    created_by: str
    version: int = 1
