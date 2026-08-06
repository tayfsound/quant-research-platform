"""Faz 196: on-chain metrik motoru — gerçek ağa karşı test ediyor (Binance/
Yahoo testlerinde kurulmuş konvansiyonla tutarlı)."""
from market_data.onchain.onchain_provider import (
    fetch_eth_gas_price_gwei,
    fetch_hash_rate_trend,
    fetch_network_activity_trend,
    fetch_solana_tps,
    fetch_usdt_total_supply,
)


def test_fetch_eth_gas_price_returns_a_real_plausible_value():
    gwei = fetch_eth_gas_price_gwei()
    assert gwei is not None
    assert gwei > 0


def test_fetch_usdt_total_supply_returns_a_real_plausible_value():
    supply = fetch_usdt_total_supply()
    assert supply is not None
    # Tether'in dolaşımdaki arzı gerçekçi olarak on milyarlarca dolar.
    assert supply > 1_000_000_000


def test_fetch_solana_tps_returns_a_real_plausible_value():
    tps = fetch_solana_tps()
    assert tps is not None
    assert tps > 0


def test_fetch_eth_gas_price_returns_none_without_infura_url(monkeypatch):
    monkeypatch.setenv("INFURA_MAINNET_URL", "")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_eth_gas_price_gwei() is None
    finally:
        get_settings.cache_clear()


def test_fetch_network_activity_trend_returns_a_real_bucket():
    result = fetch_network_activity_trend()
    assert result in ("rising", "falling", "stable")


def test_fetch_hash_rate_trend_returns_a_real_bucket():
    result = fetch_hash_rate_trend()
    assert result in ("rising", "falling", "stable")


def test_fetch_solana_tps_returns_none_without_helius_key(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_solana_tps() is None
    finally:
        get_settings.cache_clear()
