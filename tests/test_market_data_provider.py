"""Phase 183 — data provider testleri."""
from unittest.mock import AsyncMock, patch

import pytest

from market_data.ingestion.data_provider import MockProvider, BinanceProvider, get_ohlcv_provider
from market_data.ingestion.ohlcv import OHLCV, from_binance_klines
from market_data.features.indicators import rsi

def test_mock_provider_returns_ohlcv():
    p = MockProvider(seed=42)
    data = p.get_ohlcv("BTCUSDT", "1m", limit=50)
    assert len(data) == 50
    assert isinstance(data[0], OHLCV)
    assert data[0].close > 0

def test_from_binance_klines():
    raw = [{"time": 1700000000000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0}]
    bars = from_binance_klines(raw)
    assert len(bars) == 1
    assert bars[0].close == 1.5

def test_indicators_on_converted():
    raw = [{"time": 1700000000000 + i*60000, "open": 100+i, "high": 101+i,
            "low": 99+i, "close": 100.5+i, "volume": 10.0} for i in range(30)]
    data = from_binance_klines(raw)
    assert 0 <= rsi(data) <= 100

def test_get_provider_default_is_mock(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_SOURCE", "mock")
    from config import get_settings
    get_settings.cache_clear()
    p = get_ohlcv_provider()
    assert isinstance(p, MockProvider)

def test_binance_fallback_on_error(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_SOURCE", "binance")
    monkeypatch.setenv("MARKET_DATA_FALLBACK_TO_MOCK", "true")
    from config import get_settings
    get_settings.cache_clear()
    with patch("exchange_gateway.binance.adapter.BinanceAdapter") as MockAdapter:
        inst = MockAdapter.return_value
        inst.connect = AsyncMock()
        inst.disconnect = AsyncMock()
        inst.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network"))
        p = BinanceProvider()
        data = p.get_ohlcv("BTCUSDT", "1m", 20)
        assert len(data) == 20


@pytest.mark.asyncio
async def test_binance_provider_works_from_inside_a_running_event_loop():
    """Real bug (found live, confirmed 2026-08-05): BinanceProvider.get_ohlcv()
    called `asyncio.run()` unconditionally, which raises RuntimeError when
    already inside a running loop — exactly the situation for any async
    FastAPI/WebSocket path (e.g. api/websocket/live_predictions.py calling
    CognitiveOrchestrator.run_cycle() synchronously from an async handler).
    The old code swallowed that RuntimeError in a generic except, silently
    fell back to mock data, and leaked an un-awaited coroutine (RuntimeWarning).
    This test itself runs inside a live event loop (pytest-asyncio), so it
    reproduces the exact failure condition against the real Binance REST API."""
    provider = BinanceProvider()
    data = provider.get_ohlcv("BTCUSDT", "1m", limit=3)
    assert len(data) == 3
    assert data[0].close > 0
