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


def test_to_onchain_writes_real_metrics_into_market_features():
    """Faz 300 — kullanıcı bulgusu: "Predictions'da onchain verileri
    dönmüyor." to_onchain() artık gerçek metrikleri (OnchainAgent'a
    giden OnChainContext'e EK olarak) ctx.market.features'a da
    onchain_ önekiyle yazıyor — Predictions.tsx (`/orchestrator/cycle`)
    SADECE ctx.market.features'ı gösterdiği için bu şart."""
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    ContextAdapter().to_onchain(ctx)

    assert "onchain_eth_gas_price_gwei" in ctx.market.features
    assert ctx.market.features["onchain_eth_gas_price_gwei"] > 0
    assert "onchain_solana_tps" in ctx.market.features


def test_to_onchain_writes_no_features_for_non_crypto_symbol():
    ctx = CognitiveCycleContext(market={"symbol": "AAPL"})
    ContextAdapter().to_onchain(ctx)

    assert not any(k.startswith("onchain_") for k in ctx.market.features)


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
    onchain_provider.clear_bitcoin_data_cache_for_tests()

    ctx = CognitiveCycleContext(market={"symbol": "ETHUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    if result.mvrv_zscore != 0.0:
        assert -2.0 < result.mvrv_zscore < 10.0
    onchain_provider.clear_bitcoin_data_cache_for_tests()


def test_to_onchain_explicit_mvrv_override_still_wins_over_real_fetch():
    ctx = CognitiveCycleContext(market={
        "symbol": "BTCUSDT",
        "raw_snapshot": {"mvrv_zscore": 5.5},
    })
    result = ContextAdapter().to_onchain(ctx)
    assert result.mvrv_zscore == 5.5


def test_to_onchain_populates_real_exchange_inflow_when_net_flow_is_material(monkeypatch):
    """Faz 367-devam — kritik bulgu: fetch_exchange_net_flow_24h_usd()
    _real_onchain_metrics()'te hesaplanıyordu ama to_onchain()'in kendisi
    onu HİÇ okumuyordu (exchange_outflow_24h/exchange_inflow_24h hep
    sabit 0.0'a düşüyordu, mvrv_zscore/stablecoin_mint_24h ile AYNI
    real_metrics.get(...) düşme deseni eksikti) — düzeltildi."""
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(onchain_provider, "fetch_exchange_net_flow_24h_usd", lambda: 200_000_000.0)

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.exchange_inflow_24h == 200_000_000.0
    assert result.exchange_outflow_24h == 0.0


def test_to_onchain_populates_real_exchange_outflow_when_net_flow_is_negative(monkeypatch):
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(onchain_provider, "fetch_exchange_net_flow_24h_usd", lambda: -300_000_000.0)

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.exchange_outflow_24h == 300_000_000.0
    assert result.exchange_inflow_24h == 0.0


def test_to_onchain_ignores_immaterial_exchange_net_flow(monkeypatch):
    """$100M maddiyet eşiğinin altındaki bir net akış (ör. borsa bakiyesi
    1 dolar bile değişse tetiklenen anlamsız bir sinyal olmasın diye)
    sessizce 0.0'da kalmalı — bkz. context_adapter.py'nin kendi notu."""
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(onchain_provider, "fetch_exchange_net_flow_24h_usd", lambda: 50_000_000.0)

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.exchange_inflow_24h == 0.0
    assert result.exchange_outflow_24h == 0.0


def test_to_onchain_explicit_exchange_flow_override_still_wins_over_real_fetch(monkeypatch):
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(onchain_provider, "fetch_exchange_net_flow_24h_usd", lambda: 500_000_000.0)

    ctx = CognitiveCycleContext(market={
        "symbol": "BTCUSDT",
        "raw_snapshot": {"exchange_inflow_24h": 42.0},
    })
    result = ContextAdapter().to_onchain(ctx)
    assert result.exchange_inflow_24h == 42.0


def test_to_onchain_sets_whale_distribution_when_dominant_exchange_balance_rises(monkeypatch):
    """Faz 367-devam — kullanıcı kararı: gerçek balina cüzdan takibi yok,
    GEÇİCİ çözüm olarak tek bir borsadaki orantısız yoğunlaşmış hareket
    kullanılıyor. Pozitif delta (bakiye ARTTI) = varlıklar borsaya
    taşınıyor = dağıtım/satış niyeti."""
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(
        onchain_provider, "fetch_whale_like_exchange_flow", lambda: ("binance-cex", 900_000_000.0)
    )

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.whale_distribution is True
    assert result.whale_accumulation is False


def test_to_onchain_sets_whale_accumulation_when_dominant_exchange_balance_falls(monkeypatch):
    """Negatif delta (bakiye AZALDI) = borsadan soğuk cüzdana çekiliyor =
    klasik biriktirme sinyali."""
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(
        onchain_provider, "fetch_whale_like_exchange_flow", lambda: ("okx", -700_000_000.0)
    )

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.whale_accumulation is True
    assert result.whale_distribution is False


def test_to_onchain_leaves_whale_flags_false_when_no_dominant_move(monkeypatch):
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(onchain_provider, "fetch_whale_like_exchange_flow", lambda: None)

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_onchain(ctx)

    assert result.whale_accumulation is False
    assert result.whale_distribution is False


def test_to_onchain_explicit_whale_override_still_wins_over_real_fetch(monkeypatch):
    import market_data.onchain.onchain_provider as onchain_provider
    monkeypatch.setattr(
        onchain_provider, "fetch_whale_like_exchange_flow", lambda: ("binance-cex", 900_000_000.0)
    )

    ctx = CognitiveCycleContext(market={
        "symbol": "BTCUSDT",
        "raw_snapshot": {"whale_distribution": False, "whale_accumulation": True},
    })
    result = ContextAdapter().to_onchain(ctx)
    assert result.whale_accumulation is True
    assert result.whale_distribution is False
