"""Borsa entegrasyon testleri (testnet)."""
import pytest


@pytest.mark.asyncio
async def test_binance_rest_connect():
    from exchange_gateway.binance.adapter import BinanceAdapter
    adapter = BinanceAdapter()
    await adapter.connect()
    assert adapter.is_connected
    await adapter.disconnect()
