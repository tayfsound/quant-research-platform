"""Market data kaynagi secici."""
import logging
from typing import Protocol
from config import get_settings
from market_data.ingestion.ohlcv import OHLCV, from_binance_klines
from market_data.ingestion.mock_adapter import MockOHLCVAdapter

logger = logging.getLogger(__name__)

class OHLCVProvider(Protocol):
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[OHLCV]: ...

class MockProvider:
    def __init__(self, seed: int = 42):
        self._adapter = MockOHLCVAdapter(seed=seed)
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[OHLCV]:
        return self._adapter.generate(n=limit)

class BinanceProvider:
    def __init__(self):
        from exchange_gateway.binance.adapter import BinanceAdapter
        self._adapter = BinanceAdapter()
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[OHLCV]:
        import asyncio
        async def _fetch():
            await self._adapter.connect()
            try:
                raw = await self._adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
                return from_binance_klines(raw)
            finally:
                await self._adapter.disconnect()
        try:
            return asyncio.run(_fetch())
        except Exception as exc:
            logger.warning("Binance fetch failed: %s", exc)
            settings = get_settings()
            if settings.MARKET_DATA_FALLBACK_TO_MOCK:
                logger.info("Falling back to mock")
                return MockProvider().get_ohlcv(symbol, timeframe, limit)
            return []

def get_ohlcv_provider(seed: int = 42) -> OHLCVProvider:
    settings = get_settings()
    if settings.MARKET_DATA_SOURCE == "binance":
        return BinanceProvider()
    return MockProvider(seed=seed)
