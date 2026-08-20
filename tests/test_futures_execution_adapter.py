"""Faz 315 — Execution Layer, Faz 1: imzalama/istek inşası/yanıt ayrıştırma,
gerçek ağ/anahtar hiç gerekmeden (httpx.MockTransport ile) doğrulanır."""
import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from contracts.exchange import OrderSide, OrderType, PlaceOrderRequest
from exchange_gateway.binance.futures_execution_adapter import (
    BinanceDuplicateOrderError,
    BinanceFuturesExecutionAdapter,
    BinanceOrderRejectedError,
    _sign,
)


def _adapter_with_transport(handler) -> BinanceFuturesExecutionAdapter:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://testnet.binancefuture.com", transport=transport)
    return BinanceFuturesExecutionAdapter(api_key="test-key", api_secret="test-secret", client=client)


def test_sign_is_a_deterministic_hmac_sha256_over_the_canonical_query_string():
    params = {"symbol": "BTCUSDT", "side": "BUY", "timestamp": 123}
    secret = "s3cr3t"
    expected = hmac.new(secret.encode(), b"symbol=BTCUSDT&side=BUY&timestamp=123", hashlib.sha256).hexdigest()
    assert _sign(params, secret) == expected


def test_place_order_sends_signed_market_order_and_parses_fill():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return httpx.Response(200, json={
            "orderId": 555, "clientOrderId": "qrpe123", "status": "FILLED",
            "executedQty": "0.5", "avgPrice": "27000.5", "side": "BUY",
        })

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=0.5, client_order_id="qrpe123",
    )
    status = adapter.place_order(req)

    assert captured["query"]["symbol"] == ["BTCUSDT"]
    assert captured["query"]["type"] == ["MARKET"]
    assert "signature" in captured["query"]
    assert status.exchange_order_id == "555"
    assert status.status == "FILLED"
    assert status.executed_qty == 0.5
    assert status.avg_price == 27000.5


def test_place_order_includes_stop_price_and_reduce_only_for_protective_orders():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return httpx.Response(200, json={
            "orderId": 556, "clientOrderId": "qrps123", "status": "NEW",
            "executedQty": "0", "avgPrice": None, "side": "SELL",
        })

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="BTCUSDT", side=OrderSide.SELL, order_type=OrderType.STOP_MARKET,
        quantity=0.5, client_order_id="qrps123", stop_price=26000.0, reduce_only=True,
    )
    adapter.place_order(req)

    assert captured["query"]["stopPrice"] == ["26000.0"]
    assert captured["query"]["reduceOnly"] == ["true"]


def test_place_order_raises_duplicate_error_on_dash_2011():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -2011, "msg": "Duplicate order sent"})

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=0.5, client_order_id="qrpe123",
    )
    with pytest.raises(BinanceDuplicateOrderError):
        adapter.place_order(req)


def test_place_order_raises_rejected_error_on_other_error_codes():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -2019, "msg": "Margin is insufficient"})

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=0.5, client_order_id="qrpe123",
    )
    with pytest.raises(BinanceOrderRejectedError):
        adapter.place_order(req)


def test_get_order_status_returns_none_when_binance_reports_order_does_not_exist():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist"})

    adapter = _adapter_with_transport(handler)
    assert adapter.get_order_status("BTCUSDT", "555") is None


def test_get_order_status_queries_by_exchange_order_id_not_client_order_id():
    """Faz 315 regresyon kilidi — decisions tablosunda koruma emirleri
    için SADECE borsanın atadığı numerik orderId kalıcı (exchange_stop_
    order_id/exchange_tp_order_id), client_order_id DEĞİL. Adaptör bu
    yüzden origClientOrderId DEĞİL orderId ile sorgulamalı."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return httpx.Response(200, json={
            "orderId": 555, "clientOrderId": "qrpe123", "status": "FILLED",
            "executedQty": "0.5", "avgPrice": "27000.5", "side": "BUY",
        })

    adapter = _adapter_with_transport(handler)
    adapter.get_order_status("BTCUSDT", "555")

    assert captured["query"]["orderId"] == ["555"]
    assert "origClientOrderId" not in captured["query"]


def test_cancel_order_swallows_already_gone_duplicate_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -2011, "msg": "Unknown order sent"})

    adapter = _adapter_with_transport(handler)
    adapter.cancel_order("BTCUSDT", "555")  # raise etmemeli


def test_get_open_position_returns_none_when_position_amt_is_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"symbol": "BTCUSDT", "positionAmt": "0"}])

    adapter = _adapter_with_transport(handler)
    assert adapter.get_open_position("BTCUSDT") is None


def test_get_open_position_returns_row_when_position_amt_nonzero():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"symbol": "BTCUSDT", "positionAmt": "0.5"}])

    adapter = _adapter_with_transport(handler)
    row = adapter.get_open_position("BTCUSDT")
    assert row["positionAmt"] == "0.5"
