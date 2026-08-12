"""Faz 247-249: exchange_gateway/binance/adapter.py::fetch_funding_rate/
fetch_open_interest — gerçek bulgu: bu iki metod yazılmıştı ama /fapi/...
(Binance FUTURES API) yollarını spot'un temel URL'ine (api.binance.com)
bağlı paylaşılan istemciyle çağırıyordu; futures uç noktaları spot alan
adında yok, gerçek bir çağrı 403 Forbidden döndürüyordu (doğrulandı,
düzeltilmeden önce). Gerçek Binance API'ye karşı test ediyor — diğer
adapter testleriyle aynı konvansiyon (kimlik gerektirmeyen genel veri)."""
import pytest

from exchange_gateway.binance.adapter import BinanceAdapter


@pytest.mark.asyncio
async def test_fetch_funding_rate_returns_a_real_plausible_value():
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        rate = await adapter.fetch_funding_rate("BTCUSDT")
    finally:
        await adapter.disconnect()

    # Binance'in normal 8 saatlik funding oranı tipik olarak ±%1'in
    # çok altında kalır — gerçekçi bir üst/alt sınır, icat edilmiş değil.
    assert -0.01 < rate < 0.01


@pytest.mark.asyncio
async def test_fetch_open_interest_returns_a_real_positive_value():
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        oi = await adapter.fetch_open_interest("BTCUSDT")
    finally:
        await adapter.disconnect()

    assert oi > 0


@pytest.mark.asyncio
async def test_fetch_funding_rate_uses_the_futures_domain_not_spot():
    """Düzeltmeden önceki gerçek hata (403 Forbidden, spot alan adı futures
    yolunu tanımıyor) bir daha geri gelmemeli — istek gerçekten
    fapi.binance.com'a gitmeli."""
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        # Hata fırlatmadan tamamlanması, doğru (futures) alan adına
        # gittiğinin kanıtı — spot alan adına gitseydi 403 fırlatırdı.
        rate = await adapter.fetch_funding_rate("ETHUSDT")
        assert isinstance(rate, float)
    finally:
        await adapter.disconnect()
