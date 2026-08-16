"""services/market_breadth.py — relative_strength_agent'ın artık piyasa
geneliyle (watchlist yerine) kıyaslama yapabilmesi için bulk 24hr ticker
kaynağı."""
from unittest.mock import MagicMock, patch

from services import market_breadth


def _reset_cache():
    market_breadth._cache["data"] = None
    market_breadth._cache["computed_at"] = 0.0


def test_fetch_market_wide_24h_returns_filters_to_usdt_pairs_and_converts_percent():
    _reset_cache()
    fake_response = MagicMock()
    fake_response.json.return_value = [
        {"symbol": "BTCUSDT", "priceChangePercent": "5.0"},
        {"symbol": "ETHBUSD", "priceChangePercent": "3.0"},  # USDT değil, elenmeli
        {"symbol": "SOLUSDT", "priceChangePercent": "-2.5"},
    ]
    fake_response.raise_for_status = lambda: None
    with patch("httpx.get", return_value=fake_response):
        result = market_breadth.fetch_market_wide_24h_returns(force_refresh=True)

    assert result == {"BTCUSDT": 0.05, "SOLUSDT": -0.025}


def test_fetch_market_wide_24h_returns_is_cached_within_ttl():
    _reset_cache()
    fake_response = MagicMock()
    fake_response.json.return_value = [{"symbol": "BTCUSDT", "priceChangePercent": "1.0"}]
    fake_response.raise_for_status = lambda: None
    with patch("httpx.get", return_value=fake_response) as mock_get:
        market_breadth.fetch_market_wide_24h_returns(force_refresh=True)
        market_breadth.fetch_market_wide_24h_returns()
        market_breadth.fetch_market_wide_24h_returns()

    assert mock_get.call_count == 1


def test_fetch_market_wide_24h_returns_fails_closed_to_stale_cache_on_network_error():
    _reset_cache()
    fake_response = MagicMock()
    fake_response.json.return_value = [{"symbol": "BTCUSDT", "priceChangePercent": "2.0"}]
    fake_response.raise_for_status = lambda: None
    with patch("httpx.get", return_value=fake_response):
        first = market_breadth.fetch_market_wide_24h_returns(force_refresh=True)
    assert first == {"BTCUSDT": 0.02}

    with patch("httpx.get", side_effect=RuntimeError("network down")):
        second = market_breadth.fetch_market_wide_24h_returns(force_refresh=True)

    # Ağ hatasında icat edilmiş bir veri değil, elimizdeki EN SON gerçek
    # (eski olsa bile) veri döner.
    assert second == {"BTCUSDT": 0.02}


def test_fetch_market_wide_24h_returns_empty_dict_when_no_cache_and_network_fails():
    _reset_cache()
    with patch("httpx.get", side_effect=RuntimeError("network down")):
        result = market_breadth.fetch_market_wide_24h_returns(force_refresh=True)
    assert result == {}
