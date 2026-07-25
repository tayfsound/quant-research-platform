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
    assert "Contrarian" in " ".join(opinion.evidence)

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
    assert "retail overheating" in " ".join(opinion.evidence).lower()
