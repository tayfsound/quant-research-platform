"""Emir gerçekleştirme motoru."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from simulator.fee_engine.calculator import FeeEngine
from simulator.latency import LatencyModel
from simulator.order_book_model.lob import SimulatedOrderBook
from simulator.slippage_model.impact import SlippageModel


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    TAKE_PROFIT = "take_profit"

class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(StrEnum):
    NEW = "new"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"

@dataclass
class Order:
    id: UUID = field(default_factory=uuid4)
    symbol: str = "BTCUSDT"
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    price: float | None = None
    stop_price: float | None = None
    leverage: float = 1.0
    status: OrderStatus = OrderStatus.NEW

@dataclass
class Fill:
    order_id: UUID
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    slippage: float
    latency_ms: int
    timestamp: datetime = field(default_factory=datetime.now)

class ExecutionEngine:
    def __init__(self):
        self.order_book = SimulatedOrderBook("BTCUSDT")
        self.fee_engine = FeeEngine()
        self.slippage_model = SlippageModel()
        self.latency_model = LatencyModel()

    def execute(self, order: Order) -> Fill:
        if order.order_type == OrderType.MARKET:
            return self._execute_market(order)
        elif order.order_type == OrderType.LIMIT:
            return self._execute_limit(order)
        else:
            return self._execute_market(order)  # fallback

    def _execute_market(self, order: Order) -> Fill:
        avg_price, slippage = self.order_book.market_order(order.side, order.quantity)
        fee = self.fee_engine.calculate(order.quantity * avg_price, is_maker=False)
        latency = self.latency_model.get_latency_ms()
        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=avg_price,
            fee=fee,
            slippage=slippage,
            latency_ms=latency,
        )

    def _execute_limit(self, order: Order) -> Fill:
        # Basitleştirilmiş: fiyat uygunsa gerçekleşir
        if order.price is None:
            return self._execute_market(order)
        avg_price = order.price
        fee = self.fee_engine.calculate(order.quantity * avg_price, is_maker=True)
        latency = self.latency_model.get_latency_ms()
        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=avg_price,
            fee=fee,
            slippage=0.0,
            latency_ms=latency,
        )
