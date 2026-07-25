"""
Risk yönetimi portları ve şemaları.
AI'dan tamamen bağımsız, sadece imzalı konfigürasyonla çalışır.
"""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel


# -- Enum'lar --
class RiskVerdictType(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REDUCED = "reduced"          # miktar azaltılarak onay

class LimitType(StrEnum):
    MAX_POSITION_SIZE = "max_position_size"
    MAX_LEVERAGE = "max_leverage"
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_EXPOSURE = "max_exposure"
    CIRCUIT_BREAKER = "circuit_breaker"

# -- Pydantic Şemaları --
class RiskLimit(BaseModel):
    id: UUID
    scope: str                    # "global" | "strategy:<id>" | "symbol:<BTCUSDT>"
    limit_type: LimitType
    value: float
    signed_hash: str              # Ed25519 imza ile doğrulanır
    effective_at: datetime
    created_by: str
    version: int

class RiskDecisionRequest(BaseModel):
    """Risk motoruna gelen karar talebi."""
    strategy_id: UUID
    symbol: str
    action: str                   # "long" | "short" | "close_long" | "close_short"
    size: float
    leverage: float
    stop_loss: float | None = None
    take_profit: float | None = None
    current_exposure: float
    current_drawdown: float
    daily_pnl: float

class RiskVerdict(BaseModel):
    request_id: UUID
    verdict: RiskVerdictType
    reason: str | None = None     # ret sebebi
    adjusted_size: float | None = None
    limit_triggered: LimitType | None = None
    evaluated_at: datetime
    rule_version: int

# -- Port --
class RiskGatePort(Protocol):
    @abstractmethod
    async def evaluate(self, request: RiskDecisionRequest) -> RiskVerdict: ...

    @abstractmethod
    async def get_active_limits(self) -> list[RiskLimit]: ...

    @abstractmethod
    async def load_limits(self, limits: list[RiskLimit]) -> None: ...
