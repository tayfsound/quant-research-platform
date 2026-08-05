"""Market data kaynagi secici."""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol
from config import get_settings
from market_data.ingestion.ohlcv import OHLCV, from_binance_klines
from market_data.ingestion.mock_adapter import MockOHLCVAdapter

logger = logging.getLogger(__name__)


def _run_coroutine_sync(coro):
    """Gerçek bug (bulundu, doğrulandı 2026-08-05): `asyncio.run(coro)` zaten
    çalışan bir event loop içinden (örn. api/websocket/live_predictions.py'nin
    async WS handler'ı, CognitiveOrchestrator.run_cycle()'ı senkron çağırıyor)
    çağrılırsa `RuntimeError: asyncio.run() cannot be called from a running
    event loop` fırlatır. `BinanceProvider.get_ohlcv()` bunu genel bir
    `except Exception` ile yutup sessizce mock veriye düşüyordu — hem gerçek
    veri hiçbir zaman gelmiyordu hem de oluşturulan coroutine hiç await
    edilmeden sızıyordu (RuntimeWarning). Şu an çalışan bir loop var mı diye
    kontrol edip, varsa coroutine'i ayrı bir thread'de (kendi event loop'uyla)
    çalıştırıyoruz — senkron çağıranlar için davranış aynı kalıyor."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

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
        async def _fetch():
            await self._adapter.connect()
            try:
                raw = await self._adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
                return from_binance_klines(raw)
            finally:
                await self._adapter.disconnect()
        try:
            return _run_coroutine_sync(_fetch())
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
