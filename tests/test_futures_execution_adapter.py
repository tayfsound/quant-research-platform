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
    _round_quantity_to_step,
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


def test_place_order_routes_protective_orders_to_the_algo_endpoint():
    """Faz 349 — GERÇEK canlı testnet doğrulamasında (mock'ların ASLA
    yakalayamayacağı bir gerçek Binance API hatasıyla, -4120
    STOP_ORDER_SWITCH_ALGO) bulundu: Binance 2025-12-09'da STOP_MARKET/
    TAKE_PROFIT_MARKET'i eski POST /fapi/v1/order'dan YENİ POST
    /fapi/v1/algoOrder'a taşıdı — triggerPrice (stopPrice DEĞİL),
    clientAlgoId (newClientOrderId DEĞİL), algoType=CONDITIONAL."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return httpx.Response(200, json={
            "algoId": 556, "clientAlgoId": "qrps123", "algoStatus": "NEW",
            "actualQty": "0", "actualPrice": None, "side": "SELL",
        })

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="BTCUSDT", side=OrderSide.SELL, order_type=OrderType.STOP_MARKET,
        quantity=0.5, client_order_id="qrps123", stop_price=26000.0, reduce_only=True,
    )
    status = adapter.place_order(req)

    assert captured["path"] == "/fapi/v1/algoOrder"
    assert captured["query"]["algoType"] == ["CONDITIONAL"]
    assert captured["query"]["triggerPrice"] == ["26000.0"]
    assert captured["query"]["clientAlgoId"] == ["qrps123"]
    assert captured["query"]["reduceOnly"] == ["true"]
    assert "stopPrice" not in captured["query"]
    assert "newClientOrderId" not in captured["query"]
    assert status.exchange_order_id == "556"
    assert status.status == "NEW"  # henüz tetiklenmemiş, actualQty=0


def test_place_order_market_still_uses_the_regular_endpoint():
    """Faz 349 sonrası regresyon kilidi: SADECE STOP_MARKET/TAKE_PROFIT_
    MARKET algo'ya taşındı — MARKET girişi eski davranışında kalmalı."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={
            "orderId": 555, "clientOrderId": "qrpe123", "status": "FILLED",
            "executedQty": "0.5", "avgPrice": "27000.5", "side": "BUY",
        })

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=0.5, client_order_id="qrpe123",
    )
    adapter.place_order(req)

    assert captured["path"] == "/fapi/v1/order"


def test_get_order_status_falls_back_to_algo_endpoint_when_not_a_regular_order():
    """Faz 349 — çağıran (position_closer.py) bir stop/hedef emrinin
    orderId'sini sorgularken artık normal endpoint'te bulunamayacak
    (algo emri) — adaptör önce normal'i dener, -2013/-2011 alınca
    SESSİZCE algo'yu dener. actualQty>0 (borsa GERÇEKTEN tetikleyip
    doldurduğunu bildiriyor) -> position_closer.py'nin beklediği
    "FILLED" statüsüne çevrilmeli, algoStatus'un ham değeri (ör.
    "TRIGGERED") DEĞİL — adaptör bu API farkını dışarı sızdırmamalı."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/order":
            return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist"})
        assert request.url.path == "/fapi/v1/algoOrder"
        return httpx.Response(200, json={
            "algoId": 556, "clientAlgoId": "qrps123", "algoStatus": "TRIGGERED",
            "actualQty": "0.5", "actualPrice": "25800.0", "side": "SELL",
        })

    adapter = _adapter_with_transport(handler)
    status = adapter.get_order_status("BTCUSDT", "556")

    assert status.status == "FILLED"
    assert status.executed_qty == 0.5
    assert status.avg_price == 25800.0


def test_cancel_order_falls_back_to_algo_endpoint_when_not_a_regular_order():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/fapi/v1/order":
            return httpx.Response(400, json={"code": -2011, "msg": "Unknown order sent"})
        assert request.url.path == "/fapi/v1/algoOrder"
        return httpx.Response(200, json={"algoId": 556, "algoStatus": "CANCELED"})

    adapter = _adapter_with_transport(handler)
    adapter.cancel_order("BTCUSDT", "556")  # raise etmemeli

    assert calls == ["/fapi/v1/order", "/fapi/v1/algoOrder"]


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


def test_set_leverage_sends_signed_request_and_returns_confirmed_value():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return httpx.Response(200, json={"symbol": "BTCUSDT", "leverage": 10, "maxNotionalValue": "1000000"})

    adapter = _adapter_with_transport(handler)
    result = adapter.set_leverage("BTCUSDT", 10)

    assert captured["path"] == "/fapi/v1/leverage"
    assert captured["query"]["symbol"] == ["BTCUSDT"]
    assert captured["query"]["leverage"] == ["10"]
    assert "signature" in captured["query"]
    assert result == 10


def test_set_leverage_returns_exchange_clipped_value_when_different_from_requested():
    """Borsa, sembolün kendi üst sınırına göre isteneni kırpabilir —
    adaptör icat edilmiş bir "istenen == uygulanan" varsayımı yapmamalı,
    borsanın döndürdüğü GERÇEK değeri aynen iletmeli."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"symbol": "BTCUSDT", "leverage": 20, "maxNotionalValue": "500000"})

    adapter = _adapter_with_transport(handler)
    result = adapter.set_leverage("BTCUSDT", 50)

    assert result == 20


def test_set_leverage_raises_rejected_error_on_binance_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -4028, "msg": "Leverage is not valid"})

    adapter = _adapter_with_transport(handler)
    with pytest.raises(BinanceOrderRejectedError):
        adapter.set_leverage("BTCUSDT", 999)


def test_round_quantity_to_step_rounds_down_to_the_real_exchange_step():
    """Faz 396 — gerçek olay: PLTRUSDT gibi hisse/emtia sınıfı semboller
    kripto gibi 8 ondalık değil, çok daha kaba bir LOT_SIZE step
    kullanıyor. AI'nin hesapladığı miktar (0.00922463) borsanın gerçek
    step'ine (0.001) hiç yuvarlanmadan gönderiliyordu -> Binance -1111
    "Precision is over the maximum defined for this asset" ile
    reddediyordu."""
    assert _round_quantity_to_step(0.00922463, 0.001) == 0.009


def test_round_quantity_to_step_never_rounds_up():
    """AI'nin kendi hesapladığı risk boyutunu ASLA genişletmemeli --
    aşağı yuvarlanmış, hesaplanandan biraz küçük bir pozisyon her zaman
    biraz büyük bir pozisyondan daha güvenli."""
    assert _round_quantity_to_step(0.0099, 0.001) == 0.009


def test_round_quantity_to_step_avoids_float_precision_errors():
    """float // ile 0.1 % 0.001 gibi işlemler ondalık kayan nokta
    hatasından dolayı yanlış basamak sayısı üretebiliyor -- Decimal
    kullanılarak bu kaçınılıyor."""
    assert _round_quantity_to_step(0.1, 0.001) == 0.1


def test_round_quantity_to_step_passes_through_when_step_size_is_zero_or_negative():
    assert _round_quantity_to_step(0.00922463, 0.0) == 0.00922463


def test_get_step_size_fetches_and_caches_lot_size_from_exchange_info():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.path == "/fapi/v1/exchangeInfo"
        return httpx.Response(200, json={
            "symbols": [
                {
                    "symbol": "PLTRUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    ],
                },
                {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.00100000", "minQty": "0.001"},
                    ],
                },
            ],
        })

    adapter = _adapter_with_transport(handler)

    assert adapter._get_step_size("PLTRUSDT") == 0.001
    assert adapter._get_step_size("BTCUSDT") == 0.001
    # ikinci sembol için de exchangeInfo TEK seferde çekilip önbelleklenmiş
    # olmalı -- tekrar ağ isteği yapılmamalı.
    assert calls == ["/fapi/v1/exchangeInfo"]


def test_get_step_size_returns_none_when_exchange_info_request_fails():
    """Fail-closed: exchangeInfo isteği başarısız olursa (ağ hatası,
    borsa çökmüş vb.) None döner -- çağıran taraf miktarı yuvarlamadan
    gönderir (eski davranış), yeni bir hataya yol açmaz."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    adapter = _adapter_with_transport(handler)
    assert adapter._get_step_size("PLTRUSDT") is None


def test_place_order_rounds_quantity_to_the_real_exchange_step_before_sending():
    """Faz 396 -- kök neden fix: PLTRUSDT gibi semboller için gönderilen
    miktar artık borsanın GERÇEK LOT_SIZE step'ine yuvarlanıyor,
    Binance -1111 reddi bir daha olmamalı."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/exchangeInfo":
            return httpx.Response(200, json={
                "symbols": [
                    {
                        "symbol": "PLTRUSDT",
                        "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001"}],
                    },
                ],
            })
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return httpx.Response(200, json={
            "orderId": 555, "clientOrderId": "qrpe123", "status": "FILLED",
            "executedQty": "0.009", "avgPrice": "185.98", "side": "BUY",
        })

    adapter = _adapter_with_transport(handler)
    req = PlaceOrderRequest(
        symbol="PLTRUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=0.00922463, client_order_id="qrpe123",
    )
    adapter.place_order(req)

    assert captured["query"]["quantity"] == ["0.009"]


def test_place_order_leaves_quantity_untouched_when_step_size_lookup_fails():
    """Fail-closed regresyon kilidi: exchangeInfo hiç dönmezse (veya
    sembol listede yoksa) adaptör eski davranışına düşer -- miktarı
    olduğu gibi gönderir, sessizce sıfıra yuvarlamaz."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/exchangeInfo":
            return httpx.Response(500, text="internal error")
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
    adapter.place_order(req)

    assert captured["query"]["quantity"] == ["0.5"]
