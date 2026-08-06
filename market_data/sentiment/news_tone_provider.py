"""Faz 215: SentimentAgent'ın "news_tone" girdisi için gerçek veri.

Önceki not "news_tone (haber metni NLP sınıflandırması gerektirir)"
diyerek yapılmamıştı — tam NLP doğru, ama CoinDesk'in gerçek, ücretsiz,
kimliksiz RSS akışı (gerçek başlıklar) üzerinde basit, şeffaf bir anahtar
kelime eşlemesi kullanmak, TradingView alarm metni normalizasyonuyla
(agents/technical_agent.py'nin zaten kullandığı desen) aynı dürüstlük
seviyesinde — "derin NLP" iddiası yok, ama uydurma da değil: gerçek
başlıklardan gerçek bir sinyal çıkarıyor."""
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

_RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"

_CACHE: tuple | None = None
_CACHE_TTL_SECONDS = 900

_BULLISH_WORDS = (
    "surge", "rally", "soar", "jump", "climb", "gain", "record high",
    "all-time high", "breakout", "adoption", "inflow", "buy the dip",
    "approve", "approval", "bullish", "recover", "rebound",
)
_BEARISH_WORDS = (
    "crash", "plunge", "sell-off", "selloff", "tumble", "slump", "drop",
    "hack", "exploit", "lawsuit", "ban", "bearish", "liquidation",
    "capitulation", "fraud", "collapse", "outflow", "warns", "risk",
)


def fetch_news_tone() -> str | None:
    global _CACHE
    if _CACHE and (time.monotonic() - _CACHE[0]) < _CACHE_TTL_SECONDS:
        return _CACHE[1]

    try:
        response = httpx.get(_RSS_URL, timeout=10, follow_redirects=True)
        response.raise_for_status()
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", response.text)
        # İlk iki <title> her zaman feed'in kendi adı (CoinDesk: ...) —
        # gerçek haber başlıkları değil.
        headlines = [t.lower() for t in titles[2:22]]
        if not headlines:
            return None

        score = 0
        for headline in headlines:
            score += sum(1 for w in _BULLISH_WORDS if w in headline)
            score -= sum(1 for w in _BEARISH_WORDS if w in headline)

        if score >= 3:
            result = "positive"
        elif score <= -3:
            result = "negative"
        else:
            result = "neutral"

        _CACHE = (time.monotonic(), result)
        return result
    except Exception as exc:
        logger.warning("News tone (CoinDesk RSS) fetch failed: %s", exc)
        return None
