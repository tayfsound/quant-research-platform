"""Faz 315 — Execution Layer, Faz 1: ExecutionService, port sınırında
sahte bir OrderExecutionPort implementasyonuyla test edilir (mevcut
MockOHLCVAdapter deseniyle aynı) — hiç HTTP/gerçek ağ yok."""
import uuid

from contracts.exchange import OrderSide, OrderStatus, PlaceOrderRequest
from services.execution_service import ExecutionService


class _FakeAdapter:
    """place_order çağrılarını sırayla verilen sabit yanıtlarla (veya
    istisnalarla) karşılar — gerçek bir borsanın davranışını taklit
    etmeden, ExecutionService'in KENDİ karar mantığını (fail-closed,
    emergency-close, reinstate) izole test edebilmek için."""

    def __init__(self, place_order_responses):
        self._responses = list(place_order_responses)
        self.placed_requests: list[PlaceOrderRequest] = []
        self.cancelled: list[tuple[str, str]] = []

    def place_order(self, req: PlaceOrderRequest) -> OrderStatus:
        self.placed_requests.append(req)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus | None:
        return None

    def cancel_order(self, symbol: str, order_id: str) -> None:
        self.cancelled.append((symbol, order_id))

    def get_open_position(self, symbol: str) -> dict | None:
        return None


def _filled(order_id: str, client_order_id: str, side: OrderSide, qty: float, price: float) -> OrderStatus:
    return OrderStatus(
        exchange_order_id=order_id, client_order_id=client_order_id, status="FILLED",
        executed_qty=qty, avg_price=price, side=side,
    )


def test_open_position_happy_path_places_entry_then_stop_then_take_profit():
    adapter = _FakeAdapter([
        _filled("1", "qrpe1", OrderSide.BUY, 0.5, 27000.0),
        _filled("2", "qrps1", OrderSide.SELL, 0.5, 0.0),
        _filled("3", "qrpt1", OrderSide.SELL, 0.5, 0.0),
    ])
    service = ExecutionService(adapter=adapter)

    result = service.open_position(
        decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG",
        quantity=0.5, stop_loss_price=26000.0, take_profit_price=28000.0,
    )

    assert result is not None
    assert result.entry_price == 27000.0
    assert result.executed_qty == 0.5
    assert result.exchange_order_id == "1"
    assert result.exchange_stop_order_id == "2"
    assert result.exchange_tp_order_id == "3"
    assert len(adapter.placed_requests) == 3
    assert adapter.placed_requests[1].reduce_only is True
    assert adapter.placed_requests[1].stop_price == 26000.0
    assert adapter.placed_requests[2].stop_price == 28000.0


def test_open_position_returns_none_when_entry_never_confirmed_filled():
    adapter = _FakeAdapter([
        OrderStatus(exchange_order_id="1", client_order_id="qrpe1", status="NEW", executed_qty=0.0, side=OrderSide.BUY),
    ])
    service = ExecutionService(adapter=adapter)

    result = service.open_position(
        decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG",
        quantity=0.5, stop_loss_price=26000.0, take_profit_price=28000.0,
    )

    assert result is None
    # Sadece giriş denendi — belirsiz bir dolumdan sonra ASLA koruma
    # emri denenmedi (uydurma bir "açık pozisyon" hiç oluşturulmadı).
    assert len(adapter.placed_requests) == 1


def test_open_position_emergency_closes_when_protective_orders_fail_after_confirmed_fill():
    adapter = _FakeAdapter([
        _filled("1", "qrpe1", OrderSide.BUY, 0.5, 27000.0),
        RuntimeError("stop order rejected"),
    ])
    service = ExecutionService(adapter=adapter)

    result = service.open_position(
        decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG",
        quantity=0.5, stop_loss_price=26000.0, take_profit_price=28000.0,
    )

    assert result is None
    # Emergency-close denemesi ayrı bir place_order çağrısı ekler (girişin
    # tersi yönde, MARKET, reduce_only) — pozisyon asla korumasız
    # bırakılmıyor.
    assert len(adapter.placed_requests) == 3
    emergency_req = adapter.placed_requests[2]
    assert emergency_req.reduce_only is True
    assert emergency_req.side == OrderSide.SELL


def test_update_stop_price_happy_path_cancels_old_and_places_new_stop():
    adapter = _FakeAdapter([
        _filled("2", "qrps2", OrderSide.SELL, 0.5, 0.0),
    ])
    service = ExecutionService(adapter=adapter)

    result = service.update_stop_price(
        decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG", quantity=0.5,
        old_stop_order_id="OLD1", old_stop_price=26000.0, new_stop_price=26500.0,
    )

    assert result.emergency_closed is False
    assert result.new_stop_order_id == "2"
    assert result.achieved_stop_price == 26500.0
    assert adapter.cancelled == [("BTCUSDT", "OLD1")]


def test_update_stop_price_reinstates_old_price_when_new_stop_placement_fails():
    adapter = _FakeAdapter([
        RuntimeError("new stop rejected"),
        _filled("3", "qrpr1", OrderSide.SELL, 0.5, 0.0),
    ])
    service = ExecutionService(adapter=adapter)

    result = service.update_stop_price(
        decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG", quantity=0.5,
        old_stop_order_id="OLD1", old_stop_price=26000.0, new_stop_price=26500.0,
    )

    assert result.emergency_closed is False
    assert result.new_stop_order_id == "3"
    # Ratchet başarısız oldu ama koruma korundu — eski (daha gevşek)
    # fiyata geri dönüldü, yeni sıkı fiyata DEĞİL.
    assert result.achieved_stop_price == 26000.0


def test_update_stop_price_emergency_closes_when_both_new_stop_and_reinstate_fail():
    adapter = _FakeAdapter([
        RuntimeError("new stop rejected"),
        RuntimeError("reinstate also rejected"),
        _filled("9", "qrpx1", OrderSide.SELL, 0.5, 25500.0),
    ])
    service = ExecutionService(adapter=adapter)

    result = service.update_stop_price(
        decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG", quantity=0.5,
        old_stop_order_id="OLD1", old_stop_price=26000.0, new_stop_price=26500.0,
    )

    assert result.emergency_closed is True
    assert result.new_stop_order_id is None
    assert result.achieved_stop_price is None
    # 3. çağrı: acil MARKET kapanış (reduce_only) — pozisyon sınırsız
    # süre korumasız bırakılmadı.
    assert len(adapter.placed_requests) == 3
    assert adapter.placed_requests[2].reduce_only is True


def test_is_configured_false_without_an_adapter_and_without_env_keys(monkeypatch):
    from config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_KEY", "")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_SECRET", "")
    get_settings.cache_clear()
    try:
        service = ExecutionService()
        assert service.is_configured() is False
        assert service.open_position(
            decision_id=uuid.uuid4(), symbol="BTCUSDT", direction="LONG",
            quantity=0.5, stop_loss_price=26000.0, take_profit_price=28000.0,
        ) is None
    finally:
        get_settings.cache_clear()
