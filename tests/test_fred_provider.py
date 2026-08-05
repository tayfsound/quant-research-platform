"""Faz 197: MacroAgent'a gerçek FRED verisi — gerçek ağa karşı test ediyor
(Binance/Yahoo/on-chain testlerinde kurulmuş konvansiyonla tutarlı)."""
import market_data.macro.fred_provider as fred_provider
from market_data.macro.fred_provider import (
    fetch_central_bank_bias,
    fetch_employment_trend,
    fetch_inflation_trend,
    fetch_liquidity_condition,
)


def test_fetch_inflation_trend_returns_a_real_recognized_category():
    assert fetch_inflation_trend() in ("rising", "falling", "stable")


def test_fetch_employment_trend_returns_a_real_recognized_category():
    assert fetch_employment_trend() in ("improving", "weakening", "stable")


def test_fetch_central_bank_bias_returns_a_real_recognized_category():
    assert fetch_central_bank_bias() in ("hawkish", "dovish", "neutral")


def test_fetch_liquidity_condition_returns_a_real_recognized_category():
    assert fetch_liquidity_condition() in ("loose", "tight", "neutral")


def test_returns_none_without_api_key(monkeypatch):
    fred_provider._CACHE.clear()
    monkeypatch.setenv("FRED_API_KEY", "")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_inflation_trend() is None
    finally:
        get_settings.cache_clear()
        fred_provider._CACHE.clear()


def test_repeated_calls_use_the_cache_not_a_fresh_network_call(monkeypatch):
    fred_provider._CACHE.clear()
    calls = {"count": 0}
    real_get = __import__("httpx").get

    def counting_get(*args, **kwargs):
        calls["count"] += 1
        return real_get(*args, **kwargs)

    monkeypatch.setattr(fred_provider.httpx, "get", counting_get)

    fetch_inflation_trend()
    fetch_inflation_trend()
    fetch_inflation_trend()

    assert calls["count"] == 1
    fred_provider._CACHE.clear()
