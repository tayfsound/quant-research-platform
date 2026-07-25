"""Binance canlı tick verisi → event bus."""
import json
from datetime import datetime
from uuid import uuid4

import websockets

from contracts.events import MarketSnapshotEvent
from events.message_bus import get_message_bus


class LiveMarketFeed:
    def __init__(self, symbol: str = "btcusdt"):
        self.symbol = symbol.lower()
        self.bus = get_message_bus()

    async def start(self):
        url = f"wss://stream.binance.com:9443/ws/{self.symbol}@trade"
        async with websockets.connect(url) as ws:
            async for msg in ws:
                data = json.loads(msg)
                event = MarketSnapshotEvent(
                    event_id=uuid4(),
                    timestamp=datetime.fromtimestamp(data["T"] / 1000),
                    source="binance",
                    symbol=self.symbol.upper(),
                    resolution="tick",
                    open=float(data["p"]),
                    high=float(data["p"]),
                    low=float(data["p"]),
                    close=float(data["p"]),
                    volume=float(data["q"]),
                    quality_score=1.0,
                )
                await self.bus.publish("market_snapshot", event.model_dump())
