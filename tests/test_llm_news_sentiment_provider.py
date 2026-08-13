"""Faz 268-sonrası — kullanıcı isteği: Reddit sentiment (Devvit politikası
nedeniyle) kapalıydı, yerine gerçek RSS başlıklarını NVIDIA LLM'e özetleten/
puanlayan yeni kaynak. get_cached()/refresh() ayrımı test ediliyor —
get_cached() ASLA ağ çağrısı yapmamalı, refresh() gerçek RSS + LLM
çağrısı yapıp önbelleği doldurmalı, hatada önbelleği bozmamalı (fail-closed,
uydurulmuş skor yok)."""
from unittest.mock import MagicMock, patch

import market_data.sentiment.llm_news_sentiment_provider as provider


def _rss_response():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.text = (
        "<rss><channel><title>Feed Adı</title>"
        "<item><title>Bitcoin rallies past key resistance</title></item>"
        "<item><title>Regulators eye new crypto framework</title></item>"
        "</channel></rss>"
    )
    return resp


def test_get_cached_never_makes_network_calls(monkeypatch):
    provider._CACHE = None
    with patch("httpx.get") as mock_get:
        score, summary = provider.get_cached()
        assert score is None
        assert summary is None
        mock_get.assert_not_called()


def test_get_cached_returns_none_when_expired():
    import time

    provider._CACHE = (time.monotonic() - provider._CACHE_TTL_SECONDS - 1, 0.5, "eski özet", 5)
    try:
        score, summary = provider.get_cached()
        assert score is None
        assert summary is None
    finally:
        provider._CACHE = None


def test_get_cached_returns_fresh_cache_value():
    import time

    provider._CACHE = (time.monotonic(), 0.4, "taze özet", 5)
    try:
        score, summary = provider.get_cached()
        assert score == 0.4
        assert summary == "taze özet"
    finally:
        provider._CACHE = None


def test_refresh_returns_none_without_api_key(monkeypatch):
    from config import get_settings

    monkeypatch.setenv("NVIDIA_API_KEY", "")
    get_settings.cache_clear()
    provider._CACHE = None
    try:
        score, summary = provider.refresh()
        assert score is None
        assert summary is None
    finally:
        get_settings.cache_clear()
        provider._CACHE = None


def test_refresh_updates_cache_on_success(monkeypatch):
    from config import get_settings

    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    get_settings.cache_clear()
    provider._CACHE = None

    mock_llm_response = MagicMock()
    mock_llm_response.json.return_value = {
        "choices": [{"message": {
            "content": '{"sentiment_score": 0.35, "summary": "Piyasa genel olarak olumlu."}'
        }}]
    }

    try:
        with patch("httpx.get", return_value=_rss_response()), \
                patch("httpx.post", return_value=mock_llm_response):
            score, summary = provider.refresh()

        assert score == 0.35
        assert summary == "Piyasa genel olarak olumlu."
        cached_score, cached_summary = provider.get_cached()
        assert cached_score == 0.35
        assert cached_summary == "Piyasa genel olarak olumlu."
    finally:
        get_settings.cache_clear()
        provider._CACHE = None


def test_refresh_does_not_clobber_existing_cache_on_failure(monkeypatch):
    import time

    from config import get_settings

    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    get_settings.cache_clear()
    provider._CACHE = (time.monotonic(), 0.2, "önceki geçerli özet", 3)

    try:
        with patch("httpx.get", side_effect=Exception("network down")):
            score, summary = provider.refresh()

        assert score is None
        assert summary is None
        cached_score, cached_summary = provider.get_cached()
        assert cached_score == 0.2
        assert cached_summary == "önceki geçerli özet"
    finally:
        get_settings.cache_clear()
        provider._CACHE = None


def test_refresh_clamps_out_of_range_score(monkeypatch):
    from config import get_settings

    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    get_settings.cache_clear()
    provider._CACHE = None

    mock_llm_response = MagicMock()
    mock_llm_response.json.return_value = {
        "choices": [{"message": {
            "content": '{"sentiment_score": 5.0, "summary": "Aşırı iyimser uydurma değer."}'
        }}]
    }

    try:
        with patch("httpx.get", return_value=_rss_response()), \
                patch("httpx.post", return_value=mock_llm_response):
            score, _ = provider.refresh()
        assert score == 1.0
    finally:
        get_settings.cache_clear()
        provider._CACHE = None
