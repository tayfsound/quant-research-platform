"""Market Data Service sprint: IngestionPipeline was never called from
anywhere, and even the original code would have crashed if it had been —
it published a MarketSnapshotEvent without the required `exchange` field.
No persistence existed anywhere: publish() had zero subscribers, and
`market_snapshots` didn't exist as a table (faz184 added it).

This proves the real, end-to-end fix against the real Binance REST API
(public market data, no credentials needed)."""
import pytest

from contracts.market_data import DataSource, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from exchange_gateway.binance.adapter import BinanceAdapter
from market_data.ingestion.pipeline import IngestionPipeline


@pytest.mark.asyncio
async def test_ingest_candles_persists_real_binance_ohlcv_to_db():
    pipeline = IngestionPipeline(BinanceAdapter())
    written = await pipeline.ingest_candles("BTCUSDT", timeframe="1m", limit=5)

    assert written == 5

    with SessionFactory.get_session() as session:
        rows = MarketDataRepository(session).get_latest_snapshots(
            DataSource.BINANCE, "BTCUSDT", Resolution.M1, limit=5
        )

    assert len(rows) == 5
    assert all(r.close > 0 for r in rows)
    # Strictly increasing timestamps, oldest to newest.
    assert all(rows[i].time < rows[i + 1].time for i in range(len(rows) - 1))


@pytest.mark.asyncio
async def test_ingest_candles_upserts_without_duplicating_on_repeat_call():
    pipeline = IngestionPipeline(BinanceAdapter())
    await pipeline.ingest_candles("ETHUSDT", timeframe="1m", limit=3)

    with SessionFactory.get_session() as session:
        first_count = len(MarketDataRepository(session).get_latest_snapshots(
            DataSource.BINANCE, "ETHUSDT", Resolution.M1, limit=1000
        ))

    await pipeline.ingest_candles("ETHUSDT", timeframe="1m", limit=3)

    with SessionFactory.get_session() as session:
        second_count = len(MarketDataRepository(session).get_latest_snapshots(
            DataSource.BINANCE, "ETHUSDT", Resolution.M1, limit=1000
        ))

    # Same 3 most-recent bars re-fetched — at most one new bar could have
    # appeared if a minute rolled over between calls, never 3 more.
    assert second_count <= first_count + 1
