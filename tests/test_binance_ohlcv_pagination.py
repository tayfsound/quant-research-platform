"""Faz 222: kullanıcı bulgusu — "geçmiş pencere 20-1000 arası çok yetersiz."
Gerçek bulgu: Binance'in /api/v3/klines'ı TEK istekte 1000 mumdan fazlasını
vermiyor (doğrulandı: limit=1001 istense bile 1000 döner). BinanceAdapter.
fetch_ohlcv artık limit>1000 için `endTime`'ı geriye kaydırarak art arda
istek atıp (pagination) birleştiriyor. Gerçek ağ üzerinden doğrulanıyor —
bu proje mock yerine gerçek API'ye karşı test etme konvansiyonunu koruyor."""
import pytest


@pytest.mark.asyncio
async def test_fetch_ohlcv_paginates_past_the_real_1000_bar_single_request_cap():
    from exchange_gateway.binance.adapter import BinanceAdapter

    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        bars = await adapter.fetch_ohlcv("BTCUSDT", "1m", limit=1500)
    finally:
        await adapter.disconnect()

    assert len(bars) == 1500
    times = [b["time"] for b in bars]
    assert times == sorted(times)  # kronolojik sırada
    assert len(set(times)) == len(times)  # üst üste binen/tekrar eden bar yok


@pytest.mark.asyncio
async def test_fetch_ohlcv_under_the_cap_is_unchanged_single_request_behaviour():
    from exchange_gateway.binance.adapter import BinanceAdapter

    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        bars = await adapter.fetch_ohlcv("BTCUSDT", "1m", limit=50)
    finally:
        await adapter.disconnect()

    assert len(bars) == 50
