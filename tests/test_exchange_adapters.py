"""Tüm adaptörlerin uyması gereken kontrat testleri."""
from datetime import UTC, datetime

import pytest


@pytest.mark.asyncio
async def test_adapter_methods_exist():
    # Her adapter get_symbols, get_order_book, fetch_ohlcv vb. içermeli
    from exchange_gateway.binance.adapter import BinanceAdapter
    adapter = BinanceAdapter()
    assert hasattr(adapter, 'get_symbols')
    assert hasattr(adapter, 'get_order_book')
    assert hasattr(adapter, 'fetch_ohlcv')


@pytest.mark.asyncio
async def test_order_book_snapshot_time_is_real_utc_not_naive_local_time():
    """Faz 231: kritik bulgu — GET /health/signals'ı canlıda doğrularken
    yakalandı. get_order_book() naive datetime.now() (yerel saat dilimi)
    kullanıyordu, ama order_book_snapshots.time (TIMESTAMP WITHOUT TIME
    ZONE) UTC olarak okunuyor — sistem yerel saati UTC'den ileriyse (CEST,
    +2), her satır gerçekte olduğundan ~2 saat "gelecekte" görünüyordu."""
    from exchange_gateway.binance.adapter import BinanceAdapter

    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        book = await adapter.get_order_book("BTCUSDT")
    finally:
        await adapter.disconnect()

    assert book.time.tzinfo is not None
    age_seconds = (datetime.now(UTC) - book.time).total_seconds()
    assert -5 < age_seconds < 30  # gerçek "şimdi" — ne gelecekte ne saatler önce
