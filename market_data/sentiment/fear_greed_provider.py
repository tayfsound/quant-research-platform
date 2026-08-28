"""Faz 198: SentimentAgent'a gerçek Crypto Fear & Greed Index —
alternative.me'nin ücretsiz, key gerektirmeyen, herkese açık API'si.

Bilinçli olarak YAPILMADI (gerçek, ücretsiz/kolay bir kaynağı yok):
social_media_sentiment (Twitter/X NLP analizi gerektirir), news_tone
(haber metni NLP sınıflandırması), google_trends_score (Google Trends
API), positioning (borsa long/short oranı — genelde ücretli/karmaşık),
volatility_index. contracts/sentiment.py'de hepsi hâlâ varsayılan
değerlerinde — icat edilmedi."""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_FNG_URL = "https://api.alternative.me/fng/"

# Endeks günde bir kez güncelleniyor — watchlist'teki her kripto sembolü
# için ayrı ayrı çekmek (her 90sn'de 3x gereksiz istek) anlamsız.
_CACHE: dict[str, tuple] = {}
_CACHE_TTL_SECONDS = 3600


def fetch_fear_greed_index() -> float | None:
    cached = _CACHE.get("fgi")
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = httpx.get(_FNG_URL, params={"limit": 1}, timeout=10)
        response.raise_for_status()
        data = response.json().get("data") or []
        if not data:
            return None
        value = float(data[0]["value"])
        _CACHE["fgi"] = (time.monotonic(), value)
        return value
    except Exception as exc:
        logger.warning("Fear & Greed Index fetch failed: %s", exc)
        return None
