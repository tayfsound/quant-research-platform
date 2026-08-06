"""Faz 215: SentimentAgent'ın news_tone girdisi için gerçek veri —
CoinDesk'in gerçek, ücretsiz RSS akışı + şeffaf anahtar kelime eşlemesi."""
from market_data.sentiment.news_tone_provider import fetch_news_tone


def test_fetch_news_tone_returns_a_real_bucket():
    result = fetch_news_tone()
    assert result in ("positive", "negative", "neutral")
