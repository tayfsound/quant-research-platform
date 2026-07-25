"""
Market Data ve Feature Store portları ve şemaları.
"""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel


# -- Enum'lar --
class DataSource(StrEnum):
    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    COINBASE = "coinbase"
    KRAKEN = "kraken"

class Resolution(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

class DataQuality(StrEnum):
    VALID = "valid"
    SUSPECT = "suspect"
    GAP = "gap"
    CORRUPT = "corrupt"

# -- Pydantic Şemaları --
class MarketSnapshot(BaseModel):
    id: UUID | None = None
    time: datetime
    exchange: DataSource
    symbol: str
    resolution: Resolution
    open: float
    high: float
    low: float
    close: float
    volume: float
    source_version: str
    quality: DataQuality = DataQuality.VALID

class OrderBookSnapshot(BaseModel):
    time: datetime
    exchange: DataSource
    symbol: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    source_version: str

class FeatureVector(BaseModel):
    time: datetime
    symbol: str
    feature_set_version: str
    values: dict[str, float]

# -- Port (Arayüz) --
class MarketDataPort(Protocol):
    @abstractmethod
    async def fetch_historical(
        self, symbol: str, resolution: Resolution, from_dt: datetime, to_dt: datetime
    ) -> list[MarketSnapshot]: ...

    @abstractmethod
    async def subscribe_realtime(self, symbol: str) -> None: ...

class FeatureQueryPort(Protocol):
    @abstractmethod
    async def get_feature_set(
        self, symbol: str, feature_ids: list[str], from_dt: datetime, to_dt: datetime
    ) -> list[FeatureVector]: ...
