"""Borsa Ağ Geçidi portları ve şemaları."""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
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


# Faz 315 — Execution Layer, Faz 1 (gerçek testnet emir gönderimi).
# Kullanıcı isteği: sistem baştan sona saf simülasyon (uydurma dolum
# fiyatı + periyodik fiyat-yoklama ile "kapandı" kararı) — BOME/MUBARAK
# örneklerinde tam olarak bu yüzden gerçek kayıp, kontrol döngüsünün
# stop seviyesini AŞMIŞ bir fiyatı geç fark etmesinden kaynaklandı.
# Gerçek bir borsa emri kendi eşleştirme motoruyla sürekli izler — bu
# port, o gerçek emir gönderimi için (MarketDataPort/AccountReadPort'un
# YANINDA, onları değiştirmeden) yeni bir arayüz tanımlıyor.
class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"


class OrderStatus(BaseModel):
    exchange_order_id: str
    client_order_id: str
    # Binance'in ham durum string'i (NEW/PARTIALLY_FILLED/FILLED/
    # CANCELED/EXPIRED/REJECTED) — icat edilmiş bir enum'a indirgenmiyor,
    # borsanın kendi sözlüğü korunuyor.
    status: str
    executed_qty: float
    avg_price: float | None = None
    side: OrderSide


class PlaceOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    # Çağıranın (services/execution_service.py) ürettiği, deterministik
    # bir idempotency anahtarı — aynı isteğin yanlışlıkla iki kez
    # gönderilmesi durumunda borsa (ve get_order_status ile bizim kendi
    # kontrolümüz) bunu ayırt edebilsin diye.
    client_order_id: str
    stop_price: float | None = None  # STOP_MARKET/TAKE_PROFIT_MARKET için zorunlu
    reduce_only: bool = False


class OrderExecutionPort(Protocol):
    """MarketDataPort'un aksine BİLEREK senkron (async DEĞİL) — bu port'u
    çağıran tüm zincir (services/decision_recorder.py::DecisionRecorder.
    record(), services/position_closer.py::close_due_positions()) baştan
    sona senkron; async'i buraya kadar taşımak (CognitiveEngine.finalize()
    dahil tüm zincire asyncio sızdırmak) gereksiz bir mimari genişleme
    olurdu. Emir gönderimi zaten nadir/gecikme-toleranslı bir çağrı —
    MarketDataPort'un sık/performans-kritik OHLCV çekmesiyle aynı
    kısıtlara tabi değil."""
    @abstractmethod
    def place_order(self, req: PlaceOrderRequest) -> OrderStatus: ...
    @abstractmethod
    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus | None: ...
    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> None: ...
    @abstractmethod
    def get_open_position(self, symbol: str) -> dict[str, Any] | None: ...
