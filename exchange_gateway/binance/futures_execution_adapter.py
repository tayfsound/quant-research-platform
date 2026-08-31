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
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from contracts.exchange import OrderSide, OrderStatus, PlaceOrderRequest

TESTNET_BASE_URL = "https://testnet.binancefuture.com"
MAINNET_BASE_URL = "https://fapi.binance.com"

_RECV_WINDOW_MS = 5000
_ORDER_TIMEOUT_SECONDS = 10.0

# Faz 349 — kritik, GERÇEK testnet doğrulamasıyla (canlı uçtan uca
# testte, mock'lu testlerin ASLA yakalayamayacağı bir gerçek Binance
# API çağrısıyla) bulundu: Binance 2025-12-09'da koşullu emirleri
# (STOP_MARKET/TAKE_PROFIT_MARKET dahil) eski POST /fapi/v1/order'dan
# YENİ bir Algo Order servisine (POST/GET/DELETE /fapi/v1/algoOrder)
# taşıdı — kırıcı bir API değişikliği (freqtrade/nautilus_trader gibi
# başka bot projelerinde de aynı -4120 "STOP_ORDER_SWITCH_ALGO" hatasıyla
# doğrulandı). Bu kod Faz 315'te (bu değişiklikten ÖNCE) yazılmıştı —
# mock'lu testler eski API sözleşmesini varsaydığı için hiç yakalamadı.
_CONDITIONAL_ORDER_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
_ORDER_NOT_FOUND_CODES = {-2013, -2011}


def _sign(params: dict[str, Any], secret: str) -> str:
    """Binance'in dokümante ettiği HMAC-SHA256 imzalama — kanonik query
    string üzerinden. Ağdan/istemciden tamamen bağımsız, saf bir
    fonksiyon olarak tutuluyor ki gerçek anahtar olmadan bile bağımsız
    olarak yeniden hesaplanıp doğrulanabilsin (bkz. testler)."""
    query_string = urlencode(params)
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()


# Faz 396 (2026-09-01) — gerçek olay: hisse/emtia sınıfı semboller
# (PLTRUSDT/NVDAUSDT/QQQUSDT/TSLAUSDT/vb.) `execution_mode_symbols`'ta
# "testnet" işaretliyken GERÇEKTEN emir denemesi yapıyordu ama HER
# SEFERİNDE Binance -1111 "Precision is over the maximum defined for
# this asset" ile reddediliyordu — miktar (ör. 0.00922463), o sembolün
# GERÇEK LOT_SIZE step'ine (bu sınıf semboller kripto gibi 8 ondalık
# değil, çok daha kaba bir step kullanıyor) hiç yuvarlanmadan
# gönderiliyordu. `services/decision_recorder.py` bu başarısızlığı
# fail-closed ele alıyordu (opens_position=False) — DAVRANIŞ DOĞRUYDU,
# ama KÖK SEBEP (borsa gerçekten emri kabul etmiyordu) hiç
# düzeltilmemişti. exchangeInfo'nun kendi `quantityPrecision`'ı (fapi
# adapter.py'de zaten okunuyordu, satır 66) sadece GÖSTERİM amaçlı bir
# rahatlık alanı — asıl KURAL LOT_SIZE filtresinin `stepSize`'ı, bu
# yüzden ondan hesaplanıyor.
def _round_quantity_to_step(quantity: float, step_size: float) -> float:
    """Miktarı, borsanın o sembol için izin verdiği GERÇEK step'e göre
    AŞAĞI yuvarlar (yukarı değil — "AI kendi risk limitini asla
    genişletemez" ilkesiyle tutarlı, hesaplanandan biraz küçük bir
    pozisyon her zaman biraz büyük bir pozisyonden daha güvenli).
    Ondalık kayan nokta hatalarından kaçınmak için Decimal kullanılıyor
    (float ile 0.00922463 // 0.001 gibi işlemler gerçek dünyada yanlış
    basamak sayısı üretebiliyor)."""
    if step_size <= 0:
        return quantity
    d_qty = Decimal(str(quantity))
    d_step = Decimal(str(step_size))
    steps = (d_qty / d_step).to_integral_value(rounding="ROUND_DOWN")
    return float(steps * d_step)


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
        # Faz 396 — sembol başına LOT_SIZE stepSize önbelleği (exchangeInfo
        # tüm sembolleri TEK istekte döndürüyor, TEK seferde çekilip
        # process ömrü boyunca saklanıyor — her emirde yeniden çekmek
        # gereksiz bir ağ isteği/hız-limiti riski olurdu, stepSize'lar
        # borsa tarafında sık değişmiyor).
        self._step_size_cache: dict[str, float] = {}

    def _get_step_size(self, symbol: str) -> float | None:
        """Sembolün GERÇEK LOT_SIZE step'i — bulunamazsa (borsa isteği
        başarısız, sembol yok vb.) None, fail-closed: çağıran taraf bu
        durumda miktarı yuvarlamadan gönderir (eski davranış, en azından
        yeni bir hataya yol açmaz)."""
        if symbol in self._step_size_cache:
            return self._step_size_cache[symbol]
        try:
            resp = self._client.get("/fapi/v1/exchangeInfo")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        for s in data.get("symbols", []):
            step = None
            for f in s.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    step = float(f["stepSize"])
                    break
            if step is not None:
                self._step_size_cache[s["symbol"]] = step
        return self._step_size_cache.get(symbol)

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

    @staticmethod
    def _parse_algo_order_status(data: dict[str, Any]) -> OrderStatus:
        """Faz 349 — Algo Order yanıtı normal emirden FARKLI alanlar
        kullanıyor (algoId/algoStatus/clientAlgoId, ve GERÇEK dolum
        actualQty/actualPrice'ta — algoStatus'un kendisi "NEW"/
        "TRIGGERED" gibi ara durumlar taşıyabiliyor). Geri kalan
        sistemin (position_closer.py'nin "FILLED" mi diye baktığı yer
        dahil) hiç değişmeden çalışmaya devam etmesi için, GERÇEKTEN
        dolmuş (actualQty>0) bir algo emri burada "FILLED"a çevriliyor
        — adaptör, borsa API'sindeki bu farkı DIŞARI SIZDIRMIYOR."""
        actual_qty_raw = data.get("actualQty")
        actual_qty = float(actual_qty_raw) if actual_qty_raw not in (None, "", "0") else 0.0
        actual_price_raw = data.get("actualPrice")
        actual_price = float(actual_price_raw) if actual_price_raw not in (None, "", "0") else None
        status = "FILLED" if actual_qty > 0 else str(data.get("algoStatus", "NEW"))
        return OrderStatus(
            exchange_order_id=str(data["algoId"]),
            client_order_id=data.get("clientAlgoId", ""),
            status=status,
            executed_qty=actual_qty,
            avg_price=actual_price,
            side=OrderSide(data["side"]),
        )

    def _place_regular_order(self, req: PlaceOrderRequest) -> OrderStatus:
        step_size = self._get_step_size(req.symbol)
        quantity = (
            _round_quantity_to_step(req.quantity, step_size)
            if step_size is not None
            else req.quantity
        )
        params: dict[str, Any] = {
            "symbol": req.symbol,
            "side": req.side.value,
            "type": req.order_type.value,
            "quantity": quantity,
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

    def _place_algo_order(self, req: PlaceOrderRequest) -> OrderStatus:
        """Faz 349 — STOP_MARKET/TAKE_PROFIT_MARKET artık BURADAN
        gönderiliyor (bkz. dosya üstündeki not). stopPrice yerine
        triggerPrice, newClientOrderId yerine clientAlgoId — Binance'in
        Algo Order API'sinin KENDİ, farklı parametre isimleri."""
        step_size = self._get_step_size(req.symbol)
        quantity = (
            _round_quantity_to_step(req.quantity, step_size)
            if step_size is not None
            else req.quantity
        )
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": req.symbol,
            "side": req.side.value,
            "type": req.order_type.value,
            "quantity": quantity,
            "clientAlgoId": req.client_order_id,
        }
        if req.stop_price is not None:
            params["triggerPrice"] = req.stop_price
        if req.reduce_only:
            params["reduceOnly"] = "true"

        resp = self._client.post("/fapi/v1/algoOrder", params=self._signed_params(params))
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        return self._parse_algo_order_status(resp.json())

    def place_order(self, req: PlaceOrderRequest) -> OrderStatus:
        """MARKET → POST /fapi/v1/order (değişmedi). STOP_MARKET/
        TAKE_PROFIT_MARKET → POST /fapi/v1/algoOrder (Faz 349, bkz.
        dosya üstündeki not). Ağ hatası/zaman aşımı burada YUTULMUYOR —
        çağıran (ExecutionService) belirsiz bir gönderimi asla
        "başarılı" saymamalı, get_order_status ile GERÇEKTEN
        sorgulamalı (fail-closed, hiçbir tahmini dolum asla uydurulmaz)."""
        if req.order_type.value in _CONDITIONAL_ORDER_TYPES:
            return self._place_algo_order(req)
        return self._place_regular_order(req)

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus | None:
        """Borsanın kendi atadığı orderId ile sorgular (client_order_id
        DEĞİL) — decisions tablosunda kalıcı olarak saklanan (exchange_
        order_id/exchange_stop_order_id/exchange_tp_order_id) alanla
        BİREBİR aynı kimlik, ekstra bir eşleme tablosu gerekmiyor.

        Faz 349 — çağıran BU kimliğin normal bir emre mi (giriş, MARKET)
        yoksa bir algo emrine mi (stop/hedef) ait olduğunu bilmiyor —
        adaptör ikisini de dener: önce normal (daha sık/gecikmeye
        duyarlı giriş-dolum kontrolü ÇOĞUNLUKLA bu), "yok" derse algo'yu
        dener. İkisi de bulamazsa None — icat edilmiş bir durum asla
        üretilmez."""
        params = {"symbol": symbol, "orderId": order_id}
        resp = self._client.get("/fapi/v1/order", params=self._signed_params(params))
        if resp.status_code == 400 and resp.json().get("code") in _ORDER_NOT_FOUND_CODES:
            return self._get_algo_order_status(order_id)
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        return self._parse_order_status(resp.json())

    def _get_algo_order_status(self, order_id: str) -> OrderStatus | None:
        resp = self._client.get("/fapi/v1/algoOrder", params=self._signed_params({"algoId": order_id}))
        if resp.status_code == 400 and resp.json().get("code") in _ORDER_NOT_FOUND_CODES:
            return None
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        return self._parse_algo_order_status(resp.json())

    def cancel_order(self, symbol: str, order_id: str) -> None:
        """Faz 349 — AYNI "önce normal, sonra algo dene" deseni (bkz.
        get_order_status). Emir (hangi tür olursa olsun) zaten yoksa
        (dolmuş/iptal edilmiş/hiç var olmamış) "iptal et" isteğinin
        amacı zaten karşılanmış sayılır, çağıranı bir hata ile
        durdurmaya gerek yok."""
        params = {"symbol": symbol, "orderId": order_id}
        resp = self._client.delete("/fapi/v1/order", params=self._signed_params(params))
        if resp.status_code == 400 and resp.json().get("code") in _ORDER_NOT_FOUND_CODES:
            self._cancel_algo_order(order_id)
            return
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()

    def _cancel_algo_order(self, order_id: str) -> None:
        resp = self._client.delete("/fapi/v1/algoOrder", params=self._signed_params({"algoId": order_id}))
        if resp.status_code == 400 and resp.json().get("code") in _ORDER_NOT_FOUND_CODES:
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

    def set_leverage(self, symbol: str, leverage: int) -> int:
        """POST /fapi/v1/leverage — Faz 367-devam, kritik bulgu: place_
        order() öncesinde borsa hesabının GERÇEK kaldıracını uygulamanın
        varsaydığıyla eşitlemek ZORUNLU (bkz. contracts/exchange.py'nin
        kendi notu — aksi halde gerçek marj/likidasyon riski uygulamanın
        hesapladığından sessizce farklı kalıyordu). Binance leverage'ı
        TAM SAYI istiyor (uygulamanın kendi ondalık, pyramid-damped
        değerleri değil) — çağıran (ExecutionService) yuvarlamadan
        sorumlu. Dönen 'leverage' alanı borsanın GERÇEKTEN uyguladığı
        değer (istenenden farklı olabilir, ör. sembolün üst sınırına
        kırpılmış) — icat edilmiş bir "başarılı" varsayımı yok."""
        params = {"symbol": symbol, "leverage": leverage}
        resp = self._client.post("/fapi/v1/leverage", params=self._signed_params(params))
        if resp.status_code >= 400:
            self._handle_error_response(resp)
        resp.raise_for_status()
        return int(resp.json()["leverage"])

    def close(self) -> None:
        self._client.close()
