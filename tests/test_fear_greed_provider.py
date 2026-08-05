"""Faz 198: SentimentAgent'a gerçek Crypto Fear & Greed Index."""
import market_data.sentiment.fear_greed_provider as fgi_provider
from market_data.sentiment.fear_greed_provider import fetch_fear_greed_index


def test_fetch_fear_greed_index_returns_a_real_value_in_range():
    fgi_provider._CACHE.clear()
    value = fetch_fear_greed_index()
    assert value is not None
    assert 0 <= value <= 100


def test_repeated_calls_use_the_cache(monkeypatch):
    fgi_provider._CACHE.clear()
    calls = {"count": 0}
    real_get = __import__("httpx").get

    def counting_get(*args, **kwargs):
        calls["count"] += 1
        return real_get(*args, **kwargs)

    monkeypatch.setattr(fgi_provider.httpx, "get", counting_get)

    fetch_fear_greed_index()
    fetch_fear_greed_index()

    assert calls["count"] == 1
    fgi_provider._CACHE.clear()
