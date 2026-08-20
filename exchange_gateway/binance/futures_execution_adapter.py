"""Faz 315 — Execution Layer, Faz 1: Binance Futures TESTNET gerçek emir
gönderimi. contracts/exchange.py::OrderExecutionPort'u implement eder.

exchange_gateway/binance/adapter.py'den (spot, salt-okunur, kimliksiz)
KASITLI OLARAK ayrı bir dosya: imzalı/authenticated futures çağrıları,
o dosyanın günlük kullanılan tek okuma yolunu bozma riskine hiç
sokulmadan eklenmeli.

Gerçek para (fapi.binance.com) bu Faz'da kod içinde bile ERİŞİLEMEZ —
testnet=True her zaman testnet.binancefuture.com'a gider; mainnet'e
geçiş ayrı, çok daha yüksek riskli, insan onaylı bir karar olmalı."""
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from contracts.exchange import OrderSide, OrderStatus, PlaceOrderRequest

TESTNET_BASE_URL = "https://testnet.binancefuture.com"
MAINNET_BASE_URL = "https://fapi.binance.com"

_RECV_WINDOW_MS = 5000
_ORDER_TIMEOUT_SECONDS = 10.0


def _sign(params: dict[str, Any], secret: str) -> str:
    """Binance'in dokümante ettiği HMAC-SHA256 imzalama — kanonik query
    string üzerinden. Ağdan/istemciden tamamen bağımsız, saf bir
    fonksiyon olarak tutuluyor ki gerçek anahtar olmadan bile bağımsız
    olarak yeniden hesaplanıp doğrulanabilsin (bkz. testler)."""
    query_string = urlencode(params)
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()


class BinanceOrderRejectedError(Exception):
    """Borsa isteği açıkça reddetti (ör. yetersiz bakiye, geçersiz
    miktar) — ağ hatasından/zaman aşımından KASITLI OLARAK ayrı bir
    hata sınıfı: çağıran (services/execution_service.py) bunu
    "kesin başarısız" olarak ele alabilir, ağ belirsizliğinde olduğu
    gibi "belki gitti mi diye kontrol et" akışına düşmez."""


class BinanceDuplicateOrderError(Exception):
    """Borsanın -2011 "Duplicate order sent" hatası — AYNI client_order_id
    ile daha önce bir emrin GERÇEKTEN gönderildiğinin kanıtı. Çağıran bunu
    "başarısız" değil "muhtemelen zaten yerleşti, durumunu sorgula"
    olarak ele almalı (idempotency)."""


class BinanceFuturesExecutionAdapter:
    """testnet=True (Faz 1'de HER ZAMAN) — mainnet_base_url'e erişim
    kodun kendisi tarafından bile mümkün değil, ayrı bir bilinçli karar
    gerektirir."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        base_url = TESTNET_BASE_URL if testnet else MAINNET_BASE_URL
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"X-MBX-APIKEY": api_key},
            timeout=_ORDER_TIMEOUT_SECONDS,
        )

    def _signed_params(self, params: dict[str, Any]) -> dict[str, Any]:
        signed = {**params, "timestamp": int(time.time() * 1000), "recvWindow": _RECV_WINDOW_MS}
        signed["signature"] = _sign(signed, self.api_secret)
        return signed

    def _handle_error_response(self, resp: httpx.Response) -> None:
        try:
            body = resp.json()
        except Exception:
            resp.raise_for_status()
            return
        code = body.get("code")
        if code == -2011:
            raise BinanceDuplicateOrderError(body.get("msg", "Duplicate order sent"))
        if code is not None:
            raise BinanceOrderRejectedError(f"Binance error {code}: {body.get('msg')}")
        resp.raise_for_status()

    @staticmethod
    def _parse_order_status(data: dict[str, Any]) -> OrderStatus:
        avg_price_raw = data.get("avgPrice")
        avg_price = float(avg_price_raw) if avg_price_raw not in (None, "0", "0.00000") else None
        return OrderStatus(
            exchange_order_id=str(data["orderId"]),
            client_order_id=data["clientOrderId"],
            status=data["status"],
            executed_qty=float(data.get("executedQty", 0.0)),
            avg_price=avg_price,
            side=OrderSide(data["side"]),
        )

    def place_order(self, req: PlaceOrderRequest) -> OrderStatus:
        """MARKET/STOP_MARKET/TAKE_PROFIT_MARKET — üçü de bu tek uç
        noktadan (POST /fapi/v1/order) gönderiliyor, tip parametresi
        borsanın hangi davranışı uygulayacağını belirliyor. Ağ hatası/
        zaman aşımı burada YUTULMUYOR — çağıran (ExecutionService)
        belirsiz bir gönderimi asla "başarılı" saymamalı, get_order_status
        ile GERÇEKTEN sorgulamalı (fail-closed, hiçbir tahmini dolum
        asla uydurulmaz)."""
        params: dict[str, Any] = {
            "symbol": req.symbol,
            "side": req.side.value,
            "type": req.order_type.value,
            "quantity": req.quantity,
            "newClientOrderId": req.client_order_id,
        }
        if req.stop_price is not None:
            params["stopPrice"] = req.stop_price
        if req.reduce_only:
            params["reduceOnly"] = "true"

        resp = self._client.post("/fapi/v1/order", params=self._signed_params(params))
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        return self._parse_order_status(resp.json())

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus | None:
        """Borsanın kendi atadığı orderId ile sorgular (client_order_id
        DEĞİL) — decisions tablosunda kalıcı olarak saklanan (exchange_
        order_id/exchange_stop_order_id/exchange_tp_order_id) alanla
        BİREBİR aynı kimlik, ekstra bir eşleme tablosu gerekmiyor. Borsa
        bu orderId'yi tanımıyorsa (ör. çok eski/temizlenmiş) None döner —
        icat edilmiş bir durum asla üretilmez."""
        params = {"symbol": symbol, "orderId": order_id}
        resp = self._client.get("/fapi/v1/order", params=self._signed_params(params))
        if resp.status_code == 400:
            body = resp.json()
            if body.get("code") == -2013:  # "Order does not exist"
                return None
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        return self._parse_order_status(resp.json())

    def cancel_order(self, symbol: str, order_id: str) -> None:
        params = {"symbol": symbol, "orderId": order_id}
        resp = self._client.delete("/fapi/v1/order", params=self._signed_params(params))
        if resp.status_code == 400:
            body = resp.json()
            if body.get("code") == -2011:
                # Emir zaten yok (dolmuş/iptal edilmiş/hiç var olmamış) —
                # "iptal et" isteğinin amacı zaten karşılanmış sayılır,
                # çağıranı bir hata ile durdurmaya gerek yok.
                return
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()

    def get_open_position(self, symbol: str) -> dict[str, Any] | None:
        """GET /fapi/v2/positionRisk — o sembolde gerçekten açık bir
        pozisyon (positionAmt != 0) yoksa None. services/execution_
        reconciliation.py ve position_closer.py'nin testnet kapanış
        kontrolü bunu kullanıyor."""
        resp = self._client.get(
            "/fapi/v2/positionRisk", params=self._signed_params({"symbol": symbol})
        )
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        rows = resp.json()
        for row in rows:
            if row.get("symbol") == symbol and float(row.get("positionAmt", 0.0)) != 0.0:
                return row
        return None

    def close(self) -> None:
        self._client.close()
