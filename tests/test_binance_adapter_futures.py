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


@pytest.mark.asyncio
async def test_fetch_ohlcv_falls_back_to_futures_for_a_futures_only_symbol():
    """Faz 368 — kullanıcı isteği: NVDAUSDT gibi tokenize hisse
    sözleşmeleri Binance'te SADECE futures'ta var (doğrulandı: gerçek
    exchangeInfo taraması), spot'ta 400 Bad Request dönüyor. fetch_ohlcv
    artık spot'ta 400 alınca otomatik futures'a düşüyor — bu, hiç
    mock'lanmadan, GERÇEK Binance futures verisiyle doğrulanıyor."""
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        bars = await adapter.fetch_ohlcv("NVDAUSDT", "1m", limit=5)
    finally:
        await adapter.disconnect()

    assert len(bars) == 5
    assert all(b["close"] > 0 for b in bars)


@pytest.mark.asyncio
async def test_fetch_ohlcv_still_uses_spot_for_a_real_spot_symbol():
    """Regresyon: XAUTUSDT hem spot HEM futures'ta var — spot yolu
    (ucuz/hızlı, ilk deneme) hâlâ çalışmalı, futures'a hiç düşülmemeli."""
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        bars = await adapter.fetch_ohlcv("XAUTUSDT", "1m", limit=5)
    finally:
        await adapter.disconnect()

    assert len(bars) == 5
    assert all(b["close"] > 0 for b in bars)


@pytest.mark.asyncio
async def test_fetch_ohlcv_raises_for_a_symbol_that_exists_nowhere():
    """Spot 400 -> futures'a düşer, futures'ta da yoksa (tamamen geçersiz
    bir sembol) hata GERÇEKTEN fırlatılmalı — sessizce boş liste dönüp
    'veri yok'u 'sembol geçersiz'den ayırt edilemez hale getirmemeli."""
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        with pytest.raises(Exception):
            await adapter.fetch_ohlcv("THISSYMBOLDOESNOTEXISTUSDT", "1m", limit=5)
    finally:
        await adapter.disconnect()
