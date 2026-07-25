"""Piyasa verisi alım hattı."""
from datetime import datetime
from uuid import uuid4

from contracts.events import MarketSnapshotEvent
from events.message_bus import get_message_bus
from exchange_gateway.binance.adapter import BinanceAdapter


class IngestionPipeline:
    def __init__(self, adapter: BinanceAdapter):
        self.adapter = adapter
        self.bus = get_message_bus()

    async def ingest_candles(self, symbol: str, timeframe: str = "1m"):
        await self.adapter.connect()
        candles = await self.adapter.fetch_ohlcv(symbol, timeframe, limit=5)
        for c in candles:
            event = MarketSnapshotEvent(
                event_id=uuid4(),
                timestamp=datetime.fromtimestamp(c["time"] / 1000),
                source="binance",
                symbol=symbol,
                resolution=timeframe,
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=c["volume"],
                quality_score=1.0,
            )
            await self.bus.publish("market_snapshot", event.model_dump())
        await self.adapter.disconnect()
