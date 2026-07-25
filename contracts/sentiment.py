"""Sentiment Domain Contracts."""
from datetime import datetime
from pydantic import BaseModel, Field

class SentimentContext(BaseModel):
    """SentimentAgent için piyasa duyarlılığı bağlamı."""
    fear_greed_index: float = 50.0        # 0-100 (0 = extreme fear, 100 = extreme greed)
    social_media_sentiment: float = 0.0   # -1 (negatif) ile +1 (pozitif) arası
    news_tone: str = "neutral"            # "positive", "negative", "neutral"
    google_trends_score: float = 50.0     # 0-100
    positioning: str = "neutral"          # "long_bias", "short_bias", "neutral"
    volatility_index: float = 20.0        # VIX veya kripto eşdeğeri
    timestamp: datetime = Field(default_factory=datetime.now)
