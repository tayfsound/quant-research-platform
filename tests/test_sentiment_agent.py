"""Sentiment Agent testleri."""
from agents.sentiment_agent import SentimentAgent
from contracts.sentiment import SentimentContext


def test_extreme_fear_generates_long():
    agent = SentimentAgent()
    ctx = SentimentContext(
        fear_greed_index=15.0,
        social_media_sentiment=-0.6,
        news_tone="negative",
        positioning="short_bias",
    )
    opinion = agent.analyze(ctx)
    assert opinion.domain.value == "sentiment"
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0
    assert "Kontraryan" in " ".join(opinion.evidence)

def test_extreme_greed_generates_short():
    agent = SentimentAgent()
    ctx = SentimentContext(
        fear_greed_index=85.0,
        social_media_sentiment=0.7,
        news_tone="positive",
        positioning="long_bias",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0

def test_neutral_sentiment_waits():
    agent = SentimentAgent()
    ctx = SentimentContext(
        fear_greed_index=50.0,
        social_media_sentiment=0.0,
        news_tone="neutral",
        positioning="neutral",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"

def test_high_volatility_reduces_confidence():
    agent = SentimentAgent()
    ctx_low_vol = SentimentContext(fear_greed_index=15.0, volatility_index=15.0)
    ctx_high_vol = SentimentContext(fear_greed_index=15.0, volatility_index=40.0)
    opinion_low = agent.analyze(ctx_low_vol)
    opinion_high = agent.analyze(ctx_high_vol)
    assert opinion_high.confidence <= opinion_low.confidence

def test_google_trends_high_retail_risk():
    agent = SentimentAgent()
    ctx = SentimentContext(
        fear_greed_index=60.0,
        google_trends_score=90.0,
    )
    opinion = agent.analyze(ctx)
    assert "aşırı ısınmasına" in " ".join(opinion.evidence).lower()


def test_feature_contributions_sum_to_the_implied_raw_score():
    agent = SentimentAgent()
    opinion = agent.analyze(SentimentContext(fear_greed_index=15.0, positioning="short_bias"))
    implied_score = sum(opinion.feature_contributions.values())
    assert abs(abs(implied_score) - opinion.confidence * 4.0) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = SentimentAgent()
    opinion = agent.analyze(SentimentContext(
        fear_greed_index=50.0, social_media_sentiment=0.0,
        news_tone="neutral", positioning="neutral",
    ))
    assert opinion.feature_contributions == {}


def test_feature_contributions_reflect_the_volatility_discount():
    """scale_all(0.7), O ANA KADAR birikmiş katkılara (fear_greed)
    uygulanmalı — sonradan eklenen positioning katkısı ETKİLENMEMELİ,
    orijinal `score = score * 0.7`'nin tam sıralamasıyla birebir aynı."""
    agent = SentimentAgent()
    low_vol = agent.analyze(SentimentContext(fear_greed_index=15.0, volatility_index=15.0, positioning="short_bias"))
    high_vol = agent.analyze(SentimentContext(fear_greed_index=15.0, volatility_index=40.0, positioning="short_bias"))
    assert abs(high_vol.feature_contributions["fear_greed"] - low_vol.feature_contributions["fear_greed"] * 0.7) < 1e-6
    assert high_vol.feature_contributions["positioning"] == low_vol.feature_contributions["positioning"]
