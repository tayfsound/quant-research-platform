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
