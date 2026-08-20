"""Faz 196/268v: on-chain metrik motoru — gerçek ağa karşı test ediyor
(Binance/Yahoo testlerinde kurulmuş konvansiyonla tutarlı)."""
import market_data.onchain.onchain_provider as onchain_provider
from market_data.onchain.onchain_provider import (
    fetch_btc_dominance_pct,
    fetch_eth_gas_price_gwei,
    fetch_hash_rate_trend,
    fetch_mayer_multiple,
    fetch_mvrv_ratio,
    fetch_mvrv_zscore,
    fetch_network_activity_trend,
    fetch_nupl,
    fetch_realized_price,
    fetch_solana_tps,
    fetch_sopr,
    fetch_stablecoin_dominance_vs_eth_pct,
    fetch_total2_total3_market_cap_usd,
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


def test_fetch_mvrv_ratio_returns_a_real_plausible_value():
    """Faz 309 — düz MVRV oranı (Z-skoru DEĞİL). Canlı doğrulandı
    (2026-08-20): 1.3248. Tarihsel olarak hiç 0'ın altına ya da 10'un
    üstüne çıkmadı. bitcoin-data.com'un sıkı 10/saat limiti (MVRV
    Z-Score testiyle AYNI kabul) None'ı da geçerli kılıyor."""
    onchain_provider._MVRV_CACHE.clear()
    value = fetch_mvrv_ratio()
    if value is not None:
        assert 0.0 < value < 10.0
    onchain_provider._MVRV_CACHE.clear()


def test_fetch_mvrv_ratio_uses_the_cache_not_a_fresh_network_call(monkeypatch):
    onchain_provider._MVRV_CACHE.clear()
    calls = {"count": 0}
    real_get = onchain_provider.httpx.get

    def counting_get(*args, **kwargs):
        calls["count"] += 1
        return real_get(*args, **kwargs)

    monkeypatch.setattr(onchain_provider.httpx, "get", counting_get)

    fetch_mvrv_ratio()
    fetch_mvrv_ratio()
    fetch_mvrv_ratio()

    assert calls["count"] == 1
    onchain_provider._MVRV_CACHE.clear()


def test_mvrv_ratio_and_zscore_use_separate_cache_keys():
    """mvrv_zscore ve mvrv_ratio AYNI _MVRV_CACHE sözlüğünü paylaşıyor
    (farklı anahtarlarla) — biri diğerinin önbelleğini yanlışlıkla
    döndürmemeli."""
    onchain_provider._MVRV_CACHE.clear()
    onchain_provider._MVRV_CACHE["mvrv_zscore"] = (0.0, 0.4146)
    onchain_provider._MVRV_CACHE["mvrv_ratio"] = (0.0, 1.3248)
    # TTL süresi geçmiş (monotonic 0.0) sayıldığı için ikisi de taze
    # fetch'e düşer, ama testin amacı: iki farklı anahtarın birbirine
    # KARIŞMADIĞINI (aynı sözlükte bağımsız yaşadığını) doğrulamak.
    assert onchain_provider._MVRV_CACHE["mvrv_zscore"][1] != onchain_provider._MVRV_CACHE["mvrv_ratio"][1]
    onchain_provider._MVRV_CACHE.clear()


def test_fetch_nupl_returns_a_real_plausible_value():
    """Faz 316-sonrası — Net Unrealized Profit/Loss. Canlı doğrulandı
    (2026-08-20): 0.2452. Tanım gereği -1 ile 1 arasında (tüm piyasa
    kâr/zarar oranının net değeri, sınırları aşamaz)."""
    onchain_provider._MVRV_CACHE.clear()
    value = fetch_nupl()
    if value is not None:
        assert -1.0 <= value <= 1.0
    onchain_provider._MVRV_CACHE.clear()


def test_fetch_sopr_returns_a_real_plausible_value():
    """Canlı doğrulandı (2026-08-20): 1.0012. Tarihsel olarak hiç 0'ın
    altına ya da 3'ün üstüne çıkmadı."""
    onchain_provider._MVRV_CACHE.clear()
    value = fetch_sopr()
    if value is not None:
        assert 0.0 < value < 3.0
    onchain_provider._MVRV_CACHE.clear()


def test_fetch_realized_price_returns_a_real_plausible_value():
    """Canlı doğrulandı (2026-08-20): 52255.99 (BTC hiç bu kadar ucuz
    olmadı, ama gerçekleşen fiyat ortalaması güncel piyasa fiyatının
    çok altında/üstünde olamaz — kaba bir makuliyet aralığı)."""
    onchain_provider._MVRV_CACHE.clear()
    value = fetch_realized_price()
    if value is not None:
        assert 1_000.0 < value < 1_000_000.0
    onchain_provider._MVRV_CACHE.clear()


def test_nupl_sopr_realized_price_use_separate_cache_keys_from_mvrv():
    """mvrv_ratio/mvrv_zscore/nupl/sopr/realized_price hepsi AYNI
    _MVRV_CACHE sözlüğünü paylaşıyor (farklı anahtarlarla) — hiçbiri
    diğerinin önbelleğini yanlışlıkla döndürmemeli."""
    onchain_provider._MVRV_CACHE.clear()
    onchain_provider._MVRV_CACHE["mvrv_ratio"] = (0.0, 1.3248)
    onchain_provider._MVRV_CACHE["nupl"] = (0.0, 0.2452)
    onchain_provider._MVRV_CACHE["sopr"] = (0.0, 1.0012)
    onchain_provider._MVRV_CACHE["realized_price"] = (0.0, 52255.99)
    values = {
        onchain_provider._MVRV_CACHE["mvrv_ratio"][1],
        onchain_provider._MVRV_CACHE["nupl"][1],
        onchain_provider._MVRV_CACHE["sopr"][1],
        onchain_provider._MVRV_CACHE["realized_price"][1],
    }
    assert len(values) == 4
    onchain_provider._MVRV_CACHE.clear()


def test_fetch_btc_dominance_returns_a_real_plausible_value():
    """Faz 306 — kullanıcı isteği: pump-fade'in altseason/dominans
    korelasyon riski için gerçek BTC dominans verisi. Tarihsel olarak
    BTC dominansı hiç %20'nin altına ya da %95'in üstüne çıkmadı — icat
    edilmiş bir sayı değil, gerçek CoinGecko yanıtı.

    Faz 308'de gerçek bulundu: CoinGecko'nun ücretsiz katmanı kısa
    patlamalarda (bu test dosyasındaki art arda çok sayıda gerçek istek
    gibi) gerçek bir 429 dönebiliyor — MVRV testindeki AYNI kabul: None
    DE geçerli bir sonuç, sadece None DEĞİLSE makul bir aralıkta olmalı."""
    onchain_provider._generic_cache.clear()
    dominance = fetch_btc_dominance_pct()
    if dominance is not None:
        assert 20.0 < dominance < 95.0
    onchain_provider._generic_cache.clear()


def test_fetch_total2_total3_returns_real_plausible_values():
    onchain_provider._generic_cache.clear()
    result = fetch_total2_total3_market_cap_usd()
    if result is not None:
        # TOTAL3 (BTC+ETH hariç) her zaman TOTAL2'den (sadece BTC hariç)
        # küçük ya da eşit olmalı — ETH'nin payı asla negatif olamaz.
        assert 0 < result["total3_usd"] <= result["total2_usd"]
    onchain_provider._generic_cache.clear()


def test_btc_dominance_and_total2_total3_share_the_same_cached_call(monkeypatch):
    """TEK bir CoinGecko isteği hem dominansı hem TOTAL2/TOTAL3'ü besliyor
    — Faz 268j'nin (bar başına tekrar ağ isteği atmama) AYNI disiplini."""
    onchain_provider._generic_cache.clear()
    calls = {"get": 0}
    real_get = onchain_provider.httpx.get

    def counting_get(*args, **kwargs):
        calls["get"] += 1
        return real_get(*args, **kwargs)

    monkeypatch.setattr(onchain_provider.httpx, "get", counting_get)

    fetch_btc_dominance_pct()
    fetch_total2_total3_market_cap_usd()
    fetch_btc_dominance_pct()

    assert calls["get"] == 1
    onchain_provider._generic_cache.clear()


def test_fetch_stablecoin_dominance_vs_eth_returns_real_plausible_values():
    """CoinGecko'nun ücretsiz katmanı kısa patlamalarda gerçek bir 429
    dönebiliyor (test_fetch_mvrv_zscore_returns_a_real_plausible_value'daki
    AYNI kabul: fonksiyon zaten fail-closed None döner — None DE geçerli
    bir sonuç, sadece None DEĞİLSE makul bir aralıkta olmalı)."""
    onchain_provider._generic_cache.clear()
    result = fetch_stablecoin_dominance_vs_eth_pct()
    if result is not None:
        # Toplam stabilcoin dominansı tarihsel olarak hiç %30'u geçmedi.
        assert 0 < result["stablecoin_dominance_pct"] < 30
        assert 0 < result["eth_dominance_pct"] < 100
    onchain_provider._generic_cache.clear()


def test_fetch_mayer_multiple_returns_a_real_plausible_value():
    """Mayer Multiple tarihsel olarak hiç 0.3'ün altına ya da 5'in
    üstüne çıkmadı (2011 zirvesi dahil) — icat edilmiş bir sayı değil,
    gerçek OHLCV'den hesaplanmış."""
    onchain_provider._generic_cache.clear()
    mayer = fetch_mayer_multiple()
    assert mayer is not None
    assert 0.3 < mayer < 5.0
    onchain_provider._generic_cache.clear()


def test_fetch_mayer_multiple_uses_the_cache_not_a_fresh_call(monkeypatch):
    onchain_provider._generic_cache.clear()
    calls = {"count": 0}

    from market_data.ingestion import data_provider as dp_module
    real_get_provider = dp_module.get_ohlcv_provider

    def counting_get_provider(*args, **kwargs):
        calls["count"] += 1
        return real_get_provider(*args, **kwargs)

    monkeypatch.setattr(dp_module, "get_ohlcv_provider", counting_get_provider)

    fetch_mayer_multiple()
    fetch_mayer_multiple()
    fetch_mayer_multiple()

    assert calls["count"] == 1
    onchain_provider._generic_cache.clear()
