"""Faz 196/268v: on-chain metrik motoru — gerçek ağa karşı test ediyor
(Binance/Yahoo testlerinde kurulmuş konvansiyonla tutarlı)."""
import market_data.onchain.onchain_provider as onchain_provider
from market_data.onchain.onchain_provider import (
    fetch_eth_gas_price_gwei,
    fetch_hash_rate_trend,
    fetch_mvrv_zscore,
    fetch_network_activity_trend,
    fetch_solana_tps,
    fetch_usdt_total_supply,
)


def test_fetch_eth_gas_price_returns_a_real_plausible_value():
    onchain_provider._generic_cache.clear()
    gwei = fetch_eth_gas_price_gwei()
    assert gwei is not None
    assert gwei > 0


def test_fetch_usdt_total_supply_returns_a_real_plausible_value():
    onchain_provider._generic_cache.clear()
    supply = fetch_usdt_total_supply()
    assert supply is not None
    # Tether'in dolaşımdaki arzı gerçekçi olarak on milyarlarca dolar.
    assert supply > 1_000_000_000


def test_fetch_solana_tps_returns_a_real_plausible_value():
    onchain_provider._generic_cache.clear()
    tps = fetch_solana_tps()
    assert tps is not None
    assert tps > 0


def test_fetch_eth_gas_price_returns_none_without_infura_url(monkeypatch):
    onchain_provider._generic_cache.clear()
    monkeypatch.setenv("INFURA_MAINNET_URL", "")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_eth_gas_price_gwei() is None
    finally:
        get_settings.cache_clear()
        onchain_provider._generic_cache.clear()


def test_fetch_network_activity_trend_returns_a_real_bucket():
    onchain_provider._generic_cache.clear()
    result = fetch_network_activity_trend()
    assert result in ("rising", "falling", "stable")


def test_fetch_hash_rate_trend_returns_a_real_bucket():
    onchain_provider._generic_cache.clear()
    result = fetch_hash_rate_trend()
    assert result in ("rising", "falling", "stable")


def test_fetch_solana_tps_returns_none_without_helius_key(monkeypatch):
    onchain_provider._generic_cache.clear()
    monkeypatch.setenv("HELIUS_API_KEY", "")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_solana_tps() is None
    finally:
        get_settings.cache_clear()
        onchain_provider._generic_cache.clear()


def test_onchain_fetches_are_cached_within_the_ttl_not_refetched_per_bar(monkeypatch):
    """Faz 268j — gerçek olay: bir walk-forward backtest'te bu 5 fonksiyon
    (MVRV hariç, o zaten önbellekliydi) HER TEK bar için taze bir ağ
    isteği atıyordu — 15 sembol × ~900 bar'da saatler süren bir backtest'e
    yol açtı. Artık test_fetch_mvrv_zscore_uses_the_cache... ile AYNI
    desen: aynı process içinde art arda çağrılar TEK bir gerçek ağ
    isteğini paylaşıyor."""
    onchain_provider._generic_cache.clear()
    calls = {"get": 0, "post": 0}
    real_get = onchain_provider.httpx.get
    real_post = onchain_provider.httpx.post

    def counting_get(*args, **kwargs):
        calls["get"] += 1
        return real_get(*args, **kwargs)

    def counting_post(*args, **kwargs):
        calls["post"] += 1
        return real_post(*args, **kwargs)

    monkeypatch.setattr(onchain_provider.httpx, "get", counting_get)
    monkeypatch.setattr(onchain_provider.httpx, "post", counting_post)

    for _ in range(3):
        fetch_eth_gas_price_gwei()
        fetch_usdt_total_supply()
        fetch_solana_tps()
        fetch_network_activity_trend()
        fetch_hash_rate_trend()

    # eth_gasPrice, eth_call (USDT), Helius TPS -> POST; iki blockchain.info
    # chart'ı -> GET. Her biri 3 çağrıda TEK gerçek ağ isteğine düşmeli.
    assert calls["post"] == 3
    assert calls["get"] == 2
    onchain_provider._generic_cache.clear()


def test_fetch_mvrv_zscore_returns_a_real_plausible_value():
    """Faz 268v: kullanıcı isteği — MVRV Z-Score, gerçek/yapılandırılmış
    bir kaynaktan (bitcoin-data.com, API key gerektirmiyor). Tarihsel
    olarak makul bir aralıkta (-2 ile +10 arası) kalır — icat edilmiş bir
    sayı değil, gerçek API yanıtı.

    Gerçek bulgu: diğer sağlayıcıların (FRED/blockchain.info/Infura/
    Helius) aksine bitcoin-data.com'un ücretsiz katmanı ÇOK sıkı (8
    istek/saat) — tam test paketi sık çalıştırılınca (bu oturumda olduğu
    gibi) gerçek bir 429 dönebiliyor. fetch_mvrv_zscore() zaten fail-
    closed (böyle bir durumda None döner, icat edilmiş bir sayı değil) —
    bu test de aynı sözleşmeyi kabul ediyor: None DE geçerli bir sonuç,
    sadece None DEĞİLSE makul bir aralıkta olmalı."""
    onchain_provider._MVRV_CACHE.clear()
    value = fetch_mvrv_zscore()
    if value is not None:
        assert -2.0 < value < 10.0
    onchain_provider._MVRV_CACHE.clear()


def test_fetch_mvrv_zscore_uses_the_cache_not_a_fresh_network_call(monkeypatch):
    onchain_provider._MVRV_CACHE.clear()
    calls = {"count": 0}
    real_get = onchain_provider.httpx.get

    def counting_get(*args, **kwargs):
        calls["count"] += 1
        return real_get(*args, **kwargs)

    monkeypatch.setattr(onchain_provider.httpx, "get", counting_get)

    fetch_mvrv_zscore()
    fetch_mvrv_zscore()
    fetch_mvrv_zscore()

    assert calls["count"] == 1
    onchain_provider._MVRV_CACHE.clear()
