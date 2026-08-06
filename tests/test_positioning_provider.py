"""Faz 215: SentimentAgent'ın positioning girdisi için gerçek veri —
Binance Futures'ın gerçekten ücretsiz/kimliksiz erişilebilen global
long/short hesap oranı. Gerçek ağa karşı test ediyor (bu oturumun
established konvansiyonu — bkz. test_yahoo_provider.py)."""
from market_data.sentiment.positioning_provider import fetch_positioning


def test_fetch_positioning_returns_a_real_bucket_for_btc():
    result = fetch_positioning("BTCUSDT")
    assert result in ("long_bias", "short_bias", "neutral")


def test_fetch_positioning_returns_none_for_a_symbol_without_futures():
    result = fetch_positioning("THISISNOTAREALFUTURESYMBOLXYZ")
    assert result is None
