"""Faz 196: ContextAdapter.to_onchain() artık gerçek on-chain metrikleri
(gas price/Solana TPS/stablecoin arz deltası) SADECE kripto sembolleri
için besliyor."""
from contracts.context import CognitiveCycleContext
from services.context_adapter import ContextAdapter


def test_to_onchain_populates_real_network_metrics_for_crypto_symbol():
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.eth_gas_price_gwei is not None
    assert result.eth_gas_price_gwei > 0
    assert result.solana_tps is not None
    assert result.solana_tps > 0


def test_to_onchain_has_no_network_metrics_for_non_crypto_symbol():
    ctx = CognitiveCycleContext(market={"symbol": "AAPL"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.eth_gas_price_gwei is None
    assert result.solana_tps is None


def test_to_onchain_explicit_override_still_wins_over_real_fetch():
    ctx = CognitiveCycleContext(market={
        "symbol": "BTCUSDT",
        "raw_snapshot": {"stablecoin_mint_24h": 555.0},
    })
    result = ContextAdapter().to_onchain(ctx)
    assert result.stablecoin_mint_24h == 555.0


def test_to_onchain_populates_real_mvrv_zscore_for_crypto_symbol():
    """Faz 268v: kullanıcı isteği — MVRV Z-Score gerçek bir kaynaktan
    (bitcoin-data.com) besleniyor, network_activity_trend/hash_rate_trend
    ile AYNI desende (Bitcoin'e özel, tüm kripto sembollerine genel bir
    piyasa koşulu olarak uygulanıyor).

    Gerçek bulgu: bitcoin-data.com'un ücretsiz katmanı sıkı bir hız
    sınırına (8 istek/saat) sahip — tam test paketi sık çalıştırılınca
    gerçek bir 429 dönebilir. fetch_mvrv_zscore() fail-closed olduğu için
    (böyle bir durumda None -> mvrv_zscore=0.0 varsayılanı) bu test de
    None/0.0 durumunu geçerli kabul ediyor, sadece gerçekten bir değer
    geldiyse makul bir aralıkta olduğunu doğruluyor."""
    import market_data.onchain.onchain_provider as onchain_provider
    onchain_provider._MVRV_CACHE.clear()

    ctx = CognitiveCycleContext(market={"symbol": "ETHUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    if result.mvrv_zscore != 0.0:
        assert -2.0 < result.mvrv_zscore < 10.0
    onchain_provider._MVRV_CACHE.clear()


def test_to_onchain_explicit_mvrv_override_still_wins_over_real_fetch():
    ctx = CognitiveCycleContext(market={
        "symbol": "BTCUSDT",
        "raw_snapshot": {"mvrv_zscore": 5.5},
    })
    result = ContextAdapter().to_onchain(ctx)
    assert result.mvrv_zscore == 5.5
