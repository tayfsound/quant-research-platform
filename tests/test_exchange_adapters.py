"""Tüm adaptörlerin uyması gereken kontrat testleri."""
import pytest


@pytest.mark.asyncio
async def test_adapter_methods_exist():
    # Her adapter get_symbols, get_order_book, fetch_ohlcv vb. içermeli
    from exchange_gateway.binance.adapter import BinanceAdapter
    adapter = BinanceAdapter()
    assert hasattr(adapter, 'get_symbols')
    assert hasattr(adapter, 'get_order_book')
    assert hasattr(adapter, 'fetch_ohlcv')
