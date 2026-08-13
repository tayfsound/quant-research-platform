"""Labeling ve Gerçek Fırsat Dataset'i testleri — Faz 444-468 (Cognitive Core 2.0)."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from analytics.opportunity_labeling import label_rejected_opportunity


def _kline(t_ms: int, open_: float, high: float, low: float, close: float) -> list:
    return [t_ms, str(open_), str(high), str(low), str(close), "100.0"]


@pytest.mark.asyncio
async def test_labels_a_real_rejected_long_opportunity_with_mocked_bars():
    base_ms = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    klines = [
        _kline(base_ms, 100, 100.2, 99.9, 100.0),
        _kline(base_ms + 60_000, 100, 101.8, 99.9, 101.5),  # MFE: +1.8%
        _kline(base_ms + 120_000, 101.5, 101.6, 99.7, 99.8),  # MAE: -0.3%
    ]
    with patch("analytics.opportunity_labeling.BinanceAdapter") as MockAdapter:
        instance = MockAdapter.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.fetch_ohlcv = AsyncMock(return_value=klines)

        result = await label_rejected_opportunity(
            "BTCUSDT", "LONG", datetime(2026, 1, 1, tzinfo=UTC), timeframe="1m",
        )

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["direction"] == "LONG"
    assert result["entry_price"] == 100.0
    assert result["mfe_pct"] > 0.017
    assert result["mae_pct"] < 0.0


@pytest.mark.asyncio
async def test_returns_none_when_the_symbol_cannot_be_fetched():
    with patch("analytics.opportunity_labeling.BinanceAdapter") as MockAdapter:
        instance = MockAdapter.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.fetch_ohlcv = AsyncMock(side_effect=Exception("symbol not found"))

        result = await label_rejected_opportunity(
            "GC=F", "LONG", datetime(2026, 1, 1, tzinfo=UTC),
        )
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_fewer_than_two_bars_are_available():
    base_ms = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    with patch("analytics.opportunity_labeling.BinanceAdapter") as MockAdapter:
        instance = MockAdapter.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.fetch_ohlcv = AsyncMock(return_value=[_kline(base_ms, 100, 100.2, 99.9, 100.0)])

        result = await label_rejected_opportunity(
            "BTCUSDT", "LONG", datetime(2026, 1, 1, tzinfo=UTC),
        )
    assert result is None
