"""Piyasa verisi alım hattı — Market Data Service sprint.

Gerçek bulgu: bu pipeline hiçbir yerden çağrılmıyordu, ve çağrılsa bile
sadece in-memory event bus'a publish ediyordu — hiçbir kalıcı subscriber
yoktu, veri publish edilir edilmez kaybolurdu. Artık gerçekten
`market_snapshots` tablosuna (faz184) yazıyor; event bus publish'i de
koruyoruz (gelecekteki canlı-yayın tüketicileri için — örn. bir WS relay —
zararsız, ekstra maliyeti yok).
"""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.events import MarketSnapshotEvent
from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from events.message_bus import get_message_bus
from exchange_gateway.binance.adapter import BinanceAdapter


class IngestionPipeline:
    def __init__(self, adapter: BinanceAdapter):
        self.adapter = adapter
        self.bus = get_message_bus()

    async def ingest_candles(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> int:
        """Binance'tan son `limit` mumu çeker, `market_snapshots`'a UPSERT
        eder (aynı bar tekrar çekilirse — henüz kapanmamış mum — günceller,
        duplicate satır oluşturmaz). Döndürdüğü sayı, yazılan bar sayısı."""
        await self.adapter.connect()
        try:
            candles = await self.adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
        finally:
            await self.adapter.disconnect()

        snapshots = [self._to_snapshot(symbol, timeframe, c) for c in candles]

        with SessionFactory.get_session() as session:
            MarketDataRepository(session).upsert_snapshots(snapshots)

        for snapshot in snapshots:
            await self.bus.publish("market_snapshot", MarketSnapshotEvent(
                event_id=uuid4(),
                timestamp=snapshot.time,
                source=snapshot.exchange.value,
                exchange=snapshot.exchange.value,
                symbol=snapshot.symbol,
                resolution=snapshot.resolution.value,
                open=snapshot.open,
                high=snapshot.high,
                low=snapshot.low,
                close=snapshot.close,
                volume=snapshot.volume,
                quality_score=1.0,
            ).model_dump())

        return len(snapshots)

    def _to_snapshot(self, symbol: str, timeframe: str, candle: dict) -> MarketSnapshot:
        return MarketSnapshot(
            time=datetime.fromtimestamp(candle["time"] / 1000, tz=UTC),
            exchange=DataSource.BINANCE,
            symbol=symbol,
            resolution=Resolution(timeframe),
            open=candle["open"],
            high=candle["high"],
            low=candle["low"],
            close=candle["close"],
            volume=candle["volume"],
            source_version="v1",
        )
