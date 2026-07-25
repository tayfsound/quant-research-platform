"""Borsa Ağ Geçidi portları ve şemaları."""
from abc import abstractmethod
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from contracts.market_data import DataSource, OrderBookSnapshot


class ExchangeConfig(BaseModel):
    name: DataSource
    api_key: str | None = None
    api_secret: str | None = None
    testnet: bool = True
    rate_limit_per_second: int = 10

class SymbolInfo(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    min_quantity: float
    max_leverage: float
    maker_fee: float
    taker_fee: float
    funding_interval_hours: int | None = None

class AccountInfo(BaseModel):
    exchange: DataSource
    balances: dict[str, float]
    total_equity_usd: float
    margin_used: float
    positions_count: int

class MarketDataPort(Protocol):
    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def disconnect(self) -> None: ...
    @abstractmethod
    async def get_symbols(self) -> list[SymbolInfo]: ...
    @abstractmethod
    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBookSnapshot: ...
    @abstractmethod
    async def subscribe_to_streams(self, symbols: list[str]) -> None: ...
    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str, since: datetime | None = None, limit: int = 1000) -> list[dict[str, Any]]: ...
    @abstractmethod
    async def fetch_funding_rate(self, symbol: str) -> float: ...
    @abstractmethod
    async def fetch_open_interest(self, symbol: str) -> float: ...

class AccountReadPort(Protocol):
    @abstractmethod
    async def get_account_info(self) -> AccountInfo: ...
    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]: ...
