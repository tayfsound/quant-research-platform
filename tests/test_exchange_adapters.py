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


@pytest.mark.asyncio
async def test_get_order_book_falls_back_to_futures_for_futures_only_symbols():
    """Faz 371 — kullanıcı bulgusu: "AI bunlarla ilgili data göremiyor,
    no data diyor" — AAPLUSDT/TSLAUSDT gibi tokenize hisse sözleşmeleri
    SADECE futures'ta var, spot /api/v3/depth 400 döner. fetch_ohlcv
    (Faz 368) zaten spot-önce-futures-yedek uyguluyordu, get_order_book
    uygulamıyordu — order_book_snapshots'a bu semboller için hiç satır
    yazılamıyordu (order_flow ajanı gerçekten veri göremiyordu)."""
    from exchange_gateway.binance.adapter import BinanceAdapter

    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        book = await adapter.get_order_book("AAPLUSDT")
    finally:
        await adapter.disconnect()

    assert book.symbol == "AAPLUSDT"
    assert len(book.bids) > 0
    assert len(book.asks) > 0


@pytest.mark.asyncio
async def test_fetch_recent_trades_falls_back_to_futures_for_futures_only_symbols():
    """get_order_book testiyle AYNI gerekçe — aggressive_buy_ratio da bu
    semboller için önceden sessizce None kalıyordu (try/except ile
    yutuluyordu, hiç çökmüyordu ama veri de hiç gelmiyordu)."""
    from exchange_gateway.binance.adapter import BinanceAdapter

    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        trades = await adapter.fetch_recent_trades("AAPLUSDT", limit=10)
    finally:
        await adapter.disconnect()

    assert len(trades) > 0
    assert all("is_buyer_maker" in t for t in trades)
