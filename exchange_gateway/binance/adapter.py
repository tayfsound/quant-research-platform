"""
Binance REST adapter — salt okunur piyasa verisi.
"""
from datetime import UTC, datetime
from typing import Any

import httpx

from config import get_settings
from contracts.exchange import OrderBookSnapshot, SymbolInfo
from contracts.market_data import DataSource
from exchange_gateway.base import BaseExchangeAdapter
from exchange_gateway.binance.rate_limit import throttle_binance_request as _throttle_binance_request

settings = get_settings()
BASE_URL = "https://api.binance.com"
# Faz 247-249 — gerçek bulgu: fetch_funding_rate/fetch_open_interest
# /fapi/... (Binance FUTURES API) yollarını, spot'un temel URL'ine
# (api.binance.com) bağlı paylaşılan istemciyle çağırıyordu — futures
# uç noktaları spot alan adında yok, gerçek bir çağrı 403 Forbidden
# döndürdü (doğrulandı). Bu iki metod hiçbir zaman gerçekten
# çalışmamış — yazılmış ama hiç uçtan uca test edilmemiş, hiçbir
# üretim kodu da çağırmadığı için fark edilmemiş.
FUTURES_BASE_URL = "https://fapi.binance.com"

# Faz 315 — hız sınırlayıcı exchange_gateway/binance/rate_limit.py'ye
# taşındı (Execution Layer'ın futures_execution_adapter.py'si de AYNI
# Redis sayacını paylaşabilsin diye) — burada sadece eski isimle
# (_throttle_binance_request) yeniden dışa aktarılıyor, bu dosyanın geri
# kalanı hiç değişmedi.


class BinanceAdapter(BaseExchangeAdapter):
    def __init__(self) -> None:
        super().__init__("binance")
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        await super().connect()
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=15.0,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        await super().disconnect()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await _throttle_binance_request()
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # --- MarketDataPort implementasyonu ---
    async def get_symbols(self) -> list[SymbolInfo]:
        data = await self._get("/api/v3/exchangeInfo")
        return [
            SymbolInfo(
                symbol=s["symbol"],
                base_asset=s["baseAsset"],
                quote_asset=s["quoteAsset"],
                price_precision=s.get("pricePrecision", 8),
                quantity_precision=s.get("quantityPrecision", 8),
                min_quantity=float(
                    next(f["minQty"] for f in s["filters"] if f["filterType"] == "LOT_SIZE")
                ),
                max_leverage=125,
                maker_fee=0.001,
                taker_fee=0.001,
            )
            for s in data["symbols"]
        ]

    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBookSnapshot:
        # Faz 371 — kullanıcı bulgusu: yeni eklenen tokenize hisse
        # sembolleri (AAPLUSDT/MSFTUSDT/GOOGLUSDT/... — SADECE futures'ta
        # var, spot'ta yok) için "AI bunlarla ilgili data göremiyor"
        # şikayeti. Kök neden: fetch_ohlcv (Faz 368) spot 400 dönünce
        # futures'a düşüyordu ama get_order_book bu yedeği hiç
        # uygulamıyordu — spot 400 fırlatınca yakalanmadan yukarı
        # patlıyordu, market_data/ingestion/pipeline.py::ingest_order_book
        # bu istisnayı hiç yakalamadığı için order_book_snapshots
        # tablosuna BU semboller için asla satır yazılmıyordu — order_flow
        # ajanı gerçekten "no data" görüyordu. fetch_ohlcv ile AYNI
        # spot-önce-futures-yedek deseni.
        try:
            data = await self._get("/api/v3/depth", {"symbol": symbol, "limit": depth})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            await _throttle_binance_request()
            resp = await self._client.get(
                f"{FUTURES_BASE_URL}/fapi/v1/depth", params={"symbol": symbol, "limit": depth}
            )
            resp.raise_for_status()
            data = resp.json()
        return OrderBookSnapshot(
            # Faz 231: kritik bulgu — yeni GET /health/signals'ı doğrularken
            # bulundu. order_book_snapshots.time naive datetime.now() (yerel
            # CEST, UTC+2) ile yazılıyordu ama kolon TIMESTAMP WITHOUT TIME
            # ZONE — Postgres bunu olduğu gibi saklıyor, geri okununca UTC
            # sanılıyor. Sonuç: her satır gerçekte ~2 saat "gelecekte"
            # görünüyordu (health check -7146s / negatif yaş ile yakaladı —
            # aynı Faz 210a bug'ının, o zaman decisions/context.py'de
            # düzeltilen, farklı bir dosyadaki tekrarı).
            time=datetime.now(UTC),
            exchange=DataSource.BINANCE,
            symbol=symbol,
            bids=[(float(b[0]), float(b[1])) for b in data["bids"]],
            asks=[(float(a[0]), float(a[1])) for a in data["asks"]],
            source_version="v1",
        )

    async def subscribe_to_streams(self, symbols: list[str]) -> None:
        pass  # WebSocket, Faz 18'de

    @staticmethod
    def _parse_klines(data: list[list]) -> list[dict[str, Any]]:
        return [
            {
                "time": d[0],
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5]),
            }
            for d in data
        ]

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: datetime | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Faz 222: kullanıcı bulgusu — "20-1000 arası çok yetersiz." Doğrulandı:
        Binance'in /api/v3/klines'ı gerçekten TEK istekte 1000 mumdan fazlasını
        vermiyor (limit=1001 istense bile sessizce 1000 döner). limit<=1000 için
        davranış birebir eskisiyle aynı (regresyon yok). limit>1000 için
        `endTime`'ı geriye doğru kaydırarak art arda 1000'er mumluk istekler
        atıp birleştiriyoruz (pagination) — borsa daha eski veri kalmayınca
        (batch, istenenden az mum dönerse) duruyoruz.

        Faz 368 — kullanıcı isteği: NVDAUSDT/XAGUSDT/QQQUSDT/SPXUSDT gibi
        tokenize hisse/emtia/endeks sözleşmeleri Binance'te SADECE futures'ta
        var, spot'ta 400 Bad Request dönüyor (doğrulandı: gerçek exchangeInfo
        taraması). Spot-önce-sonra-futures-yedek: önce spot denenir (ucuz,
        basit — XAUTUSDT gibi hem spot HEM futures'ta olan semboller için
        değişmeyen, hızlı yol), spot 400 (geçersiz sembol) dönerse AYNI
        pagination mantığıyla futures uç noktasına (fapi.binance.com)
        düşülür. Diğer hata kodları (429/5xx gibi) yeniden fırlatılır —
        SADECE 'bu sembol spot'ta hiç yok' durumu futures'a düşüyor."""
        try:
            return await self._fetch_klines_paginated(symbol, timeframe, since, limit, use_futures=False)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            return await self._fetch_klines_paginated(symbol, timeframe, since, limit, use_futures=True)

    async def _fetch_klines_paginated(
        self, symbol: str, timeframe: str, since: datetime | None, limit: int, use_futures: bool,
    ) -> list[dict[str, Any]]:
        path = f"{FUTURES_BASE_URL}/fapi/v1/klines" if use_futures else "/api/v3/klines"

        async def _get_klines(params: dict[str, Any]) -> list:
            if use_futures:
                await _throttle_binance_request()
                resp = await self._client.get(path, params=params)
                resp.raise_for_status()
                return resp.json()
            return await self._get(path, params)

        if limit <= 1000:
            params: dict[str, Any] = {"symbol": symbol, "interval": timeframe, "limit": limit}
            if since:
                params["startTime"] = int(since.timestamp() * 1000)
            data = await _get_klines(params)
            return self._parse_klines(data)

        all_bars: list[dict[str, Any]] = []
        end_time: int | None = None
        remaining = limit
        while remaining > 0:
            batch_limit = min(1000, remaining)
            params = {"symbol": symbol, "interval": timeframe, "limit": batch_limit}
            if end_time is not None:
                params["endTime"] = end_time
            if since:
                params["startTime"] = int(since.timestamp() * 1000)
            data = await _get_klines(params)
            if not data:
                break
            all_bars = self._parse_klines(data) + all_bars
            remaining -= len(data)
            end_time = data[0][0] - 1
            if len(data) < batch_limit:
                break
        return all_bars[-limit:]

    async def fetch_recent_trades(self, symbol: str, limit: int = 200) -> list[dict[str, Any]]:
        """Faz 214: kimliksiz/genel erişilebilen son-işlemler uç noktası —
        isBuyerMaker alanı gerçek taker yönünü verir (False = agresif alış,
        alıcı taker; True = agresif satış, satıcı taker). OrderFlowAgent'ın
        aggressive_buy_ratio girdisi buradan geliyor — önceden hep sabit
        0.5 (tam nötr) idi, gerçek veri kaynağı hiç yoktu."""
        # Faz 371 — get_order_book ile AYNI spot-önce-futures-yedek gerekçesi
        # (SADECE futures'ta olan tokenize hisse sembolleri için).
        try:
            data = await self._get("/api/v3/trades", {"symbol": symbol, "limit": limit})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            await _throttle_binance_request()
            resp = await self._client.get(
                f"{FUTURES_BASE_URL}/fapi/v1/trades", params={"symbol": symbol, "limit": limit}
            )
            resp.raise_for_status()
            data = resp.json()
        return [{"is_buyer_maker": bool(t["isBuyerMaker"])} for t in data]

    async def fetch_funding_rate(self, symbol: str) -> float:
        # httpx: client.get()'e MUTLAK bir URL verilirse, istemcinin kendi
        # base_url'i (spot) yok sayılır — bu iki çağrı futures alan adına
        # gider, self._get()'in spot-varsayılan davranışı bozulmadan.
        await _throttle_binance_request()
        resp = await self._client.get(f"{FUTURES_BASE_URL}/fapi/v1/fundingRate", params={"symbol": symbol, "limit": 1})
        resp.raise_for_status()
        data = resp.json()
        return float(data[0]["fundingRate"])

    async def fetch_open_interest(self, symbol: str) -> float:
        await _throttle_binance_request()
        resp = await self._client.get(f"{FUTURES_BASE_URL}/fapi/v1/openInterest", params={"symbol": symbol})
        resp.raise_for_status()
        data = resp.json()
        return float(data["openInterest"])
