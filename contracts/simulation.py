"""
Paper Trading Simülasyon portları ve şemaları.
"""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel


# -- Enum'lar --
class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"
    TAKE_PROFIT = "take_profit"

class OrderStatus(StrEnum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class FillReason(StrEnum):
    NORMAL = "normal"
    LIQUIDATION = "liquidation"
    STOP_TRIGGERED = "stop_triggered"
    TAKE_PROFIT_TRIGGERED = "take_profit_triggered"

# -- Pydantic Şemaları --
class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    leverage: float = 1.0
    strategy_id: UUID

class SimulatedFillEvent(BaseModel):
    time: datetime
    order_id: UUID
    strategy_id: UUID
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    fee_currency: str = "USDT"
    slippage: float
    latency_ms: int
    order_type: OrderType
    leverage: float
    reason: FillReason = FillReason.NORMAL
    liquidation: bool = False

class Position(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: float
    liquidation_price: float | None = None
    margin_used: float

class PortfolioSnapshot(BaseModel):
    time: datetime
    balance: float
    equity: float
    margin_used: float
    free_margin: float
    positions: list[Position]
    daily_pnl: float
    total_pnl: float

# -- Port --
class OrderSimulationPort(Protocol):
    @abstractmethod
    async def place_order(self, request: OrderRequest) -> SimulatedFillEvent: ...

    @abstractmethod
    async def cancel_order(self, order_id: UUID) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_portfolio_snapshot(self) -> PortfolioSnapshot: ...
