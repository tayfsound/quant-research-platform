"""Faz 410 — kullanıcı bulgusu: sentiment_agent'ın google_trends_score
alanı hiçbir zaman gerçek bir veri kaynağına bağlanmamıştı, hep varsayılan
50.0'da (tam nötr) donuk kalıyordu. test_fred_provider.py ile AYNI
konvansiyon (gerçek ağa karşı test)."""
import market_data.sentiment.google_trends_provider as google_trends_provider
from market_data.sentiment.google_trends_provider import _base_symbol, fetch_google_trends_score


def test_base_symbol_strips_known_quote_suffixes():
    assert _base_symbol("BTCUSDT") == "BTC"
    assert _base_symbol("ETHBUSD") == "ETH"
    assert _base_symbol("PAXGUSDC") == "PAXG"
    assert _base_symbol("XAUTFDUSD") == "XAUT"


def test_base_symbol_leaves_unrecognized_suffix_alone():
    """Vadeli işlem/endeks gibi USDT/BUSD/USDC/FDUSD ile bitmeyen
    semboller (ör. GC=F) olduğu gibi kalmalı — icat edilmiş bir
    ayrıştırma yapılmıyor."""
    assert _base_symbol("GC=F") == "GC=F"


def test_fetch_google_trends_score_returns_a_real_0_100_range_or_none():
    """Gerçek ağa karşı: ya Google'ın kendi 0-100 ölçeğinde gerçek bir
    değer ya da (rate-limit/ağ hatası) fail-closed None."""
    result = fetch_google_trends_score("BTCUSDT")
    assert result is None or (0.0 <= result <= 100.0)


def test_repeated_calls_use_the_cache_not_a_fresh_network_call(monkeypatch):
    google_trends_provider._CACHE.clear()
    calls = {"count": 0}

    class _FakeTrendReq:
        def __init__(self, *a, **k):
            pass

        def build_payload(self, *a, **k):
            calls["count"] += 1

        def interest_over_time(self):
            import pandas as pd
            return pd.DataFrame({"Bitcoin": [42.0]})

    monkeypatch.setattr("pytrends.request.TrendReq", _FakeTrendReq)

    fetch_google_trends_score("BTCUSDT")
    fetch_google_trends_score("BTCUSDT")
    fetch_google_trends_score("BTCUSDT")

    assert calls["count"] == 1
    google_trends_provider._CACHE.clear()


def test_unrecognized_symbol_falls_back_to_the_raw_base_symbol(monkeypatch):
    google_trends_provider._CACHE.clear()
    captured = {}

    class _FakeTrendReq:
        def __init__(self, *a, **k):
            pass

        def build_payload(self, keywords, **k):
            captured["query"] = keywords[0]

        def interest_over_time(self):
            import pandas as pd
            return pd.DataFrame({captured["query"]: [10.0]})

    monkeypatch.setattr("pytrends.request.TrendReq", _FakeTrendReq)

    fetch_google_trends_score("SUIUSDT")
    assert captured["query"] == "SUI"
    google_trends_provider._CACHE.clear()


def test_network_failure_is_cached_as_none_not_retried_every_call(monkeypatch):
    google_trends_provider._CACHE.clear()
    calls = {"count": 0}

    class _FailingTrendReq:
        def __init__(self, *a, **k):
            calls["count"] += 1
            raise ConnectionError("simulated network failure")

    monkeypatch.setattr("pytrends.request.TrendReq", _FailingTrendReq)

    assert fetch_google_trends_score("BTCUSDT") is None
    assert fetch_google_trends_score("BTCUSDT") is None

    assert calls["count"] == 1
    google_trends_provider._CACHE.clear()
