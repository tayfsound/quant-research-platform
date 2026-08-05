"""Binance canlı trade akışı — gerçekten DB'ye yazıyor + çoklu sembol.

Gerçek bulgu (2026-08-05): bu sınıf hiçbir yerden çağrılmıyordu, ve
`MarketSnapshotEvent`'i zorunlu `exchange` alanı olmadan construct
ediyordu — hiç çalıştırılmamış olduğu için yakalanmamış bir
`ValidationError` (aynı desen `market_data/ingestion/pipeline.py`'de
bulunup düzeltilen bug). Ayrıca sadece event bus'a publish ediyordu —
kalıcı subscriber yoktu, veri hiçbir zaman `market_trades`'e ulaşmıyordu.
"""
import json
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

import websockets

from contracts.events import MarketSnapshotEvent
from contracts.market_data import DataSource
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from events.message_bus import get_message_bus


class LiveMarketFeed:
    def __init__(self, symbols: Iterable[str] = ("btcusdt",)):
        self.symbols = [s.lower() for s in symbols]
        self.bus = get_message_bus()

    def _stream_url(self) -> str:
        if len(self.symbols) == 1:
            return f"wss://stream.binance.com:9443/ws/{self.symbols[0]}@trade"
        streams = "/".join(f"{s}@trade" for s in self.symbols)
        return f"wss://stream.binance.com:9443/stream?streams={streams}"

    async def start(self, max_messages: int | None = None):
        """max_messages: testlerde sonsuz döngüye girmeden gerçek WS'e karşı
        doğrulama yapabilmek için — production'da None (sınırsız)."""
        url = self._stream_url()
        count = 0
        async with websockets.connect(url) as ws:
            async for msg in ws:
                raw = json.loads(msg)
                data = raw["data"] if "data" in raw and "stream" in raw else raw
                await self.handle_trade_message(data)
                count += 1
                if max_messages is not None and count >= max_messages:
                    break

    async def handle_trade_message(self, data: dict) -> None:
        """Tek bir Binance trade mesajını işler — WS bağlantısından ayrı,
        gerçek bir WS olmadan da test edilebilir."""
        symbol = data["s"].upper() if "s" in data else self.symbols[0].upper()
        price = float(data["p"])
        quantity = float(data["q"])
        trade_time = datetime.fromtimestamp(data["T"] / 1000, tz=UTC)
        # Binance: "m" = is buyer the market maker. True ise satıcı taker
        # (agresif satış), False ise alıcı taker (agresif alış).
        side = "sell" if data.get("m") else "buy"

        with SessionFactory.get_session() as session:
            MarketDataRepository(session).save_trade(
                exchange=DataSource.BINANCE,
                symbol=symbol,
                price=price,
                quantity=quantity,
                time=trade_time,
                side=side,
            )

        await self.bus.publish("market_snapshot", MarketSnapshotEvent(
            event_id=uuid4(),
            timestamp=trade_time,
            source="binance",
            exchange="binance",
            symbol=symbol,
            resolution="1m",
            open=price, high=price, low=price, close=price,
            volume=quantity,
            quality_score=1.0,
        ).model_dump())
