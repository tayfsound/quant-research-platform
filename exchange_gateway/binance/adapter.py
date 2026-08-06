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

settings = get_settings()
BASE_URL = "https://api.binance.com"


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
        data = await self._get("/api/v3/depth", {"symbol": symbol, "limit": depth})
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
        (batch, istenenden az mum dönerse) duruyoruz."""
        if limit <= 1000:
            params: dict[str, Any] = {"symbol": symbol, "interval": timeframe, "limit": limit}
            if since:
                params["startTime"] = int(since.timestamp() * 1000)
            data = await self._get("/api/v3/klines", params)
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
            data = await self._get("/api/v3/klines", params)
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
        data = await self._get("/api/v3/trades", {"symbol": symbol, "limit": limit})
        return [{"is_buyer_maker": bool(t["isBuyerMaker"])} for t in data]

    async def fetch_funding_rate(self, symbol: str) -> float:
        data = await self._get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": 1})
        return float(data[0]["fundingRate"])

    async def fetch_open_interest(self, symbol: str) -> float:
        data = await self._get("/fapi/v1/openInterest", {"symbol": symbol})
        return float(data["openInterest"])
