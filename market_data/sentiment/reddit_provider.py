"""Faz 230: kullanıcı isteği — sosyal medya sentiment. Faz 219'da Reddit'in
genel, kimliksiz JSON API'si denendi ve 403 döndüğü doğrulandı (Reddit
artık kimliksiz erişimi tamamen engelliyor). Gerçek veri için Reddit'in
tamamen ücretsiz OAuth2 "script" uygulaması gerekiyor — reddit.com/prefs/
apps üzerinden, kredi kartı/ücret gerektirmeden, birkaç dakikada
kaydedilebiliyor. client_credentials akışı (kullanıcı hesabı GEREKTİRMEZ,
sadece uygulamanın kendi client_id/secret'ı) ile salt-okunur genel
gönderilere erişiliyor.

Faz 215'teki news_tone_provider.py ile AYNI dürüstlük seviyesi: "derin NLP
sentiment analizi" iddiası yok — gerçek başlıklar üzerinde şeffaf bir
anahtar kelime sayımı. contracts/sentiment.py::social_media_sentiment
float (-1..+1) beklediği için (news_tone'un aksine, o bir bucket string)
sonuç burada bir orana normalize ediliyor."""
import logging
import re
import time

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_USER_AGENT = "quant-research-platform-sentiment/1.0"

_CACHE: tuple | None = None
_CACHE_TTL_SECONDS = 900

# news_tone_provider.py'deki listeyle aynı aile — kripto-topluluk diline
# (Reddit) uyacak birkaç ek terimle.
_BULLISH_WORDS = (
    "surge", "rally", "soar", "moon", "bullish", "breakout", "adoption",
    "all-time high", "ath", "buy the dip", "accumulate", "undervalued",
    "gain", "pump", "recover", "rebound",
)
_BEARISH_WORDS = (
    "crash", "plunge", "dump", "bearish", "sell-off", "selloff", "rug",
    "scam", "hack", "exploit", "liquidation", "capitulation", "fraud",
    "collapse", "warns", "overvalued", "bubble",
)

_NORMALIZATION_CAP = 10  # net kelime farkı ±10'da ±1.0'a doyar


def _fetch_access_token() -> str | None:
    settings = get_settings()
    if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
        return None
    try:
        response = httpx.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as exc:
        logger.warning("Reddit OAuth token fetch failed: %s", exc)
        return None


def fetch_social_sentiment(subreddit: str = "CryptoCurrency", limit: int = 25) -> float | None:
    """Son N "hot" gönderi başlığından -1..+1 aralığında bir skor. Kayıt
    yapılmadıysa (REDDIT_CLIENT_ID/SECRET boş) None döner — fail-closed,
    fail-fake değil, aynı FRED_API_KEY/HELIUS_API_KEY konvansiyonu."""
    global _CACHE
    if _CACHE and (time.monotonic() - _CACHE[0]) < _CACHE_TTL_SECONDS:
        return _CACHE[1]

    token = _fetch_access_token()
    if not token:
        return None

    try:
        response = httpx.get(
            f"https://oauth.reddit.com/r/{subreddit}/hot",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {token}", "User-Agent": _USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        posts = response.json()["data"]["children"]
        titles = [(p.get("data") or {}).get("title", "") for p in posts]
    except Exception as exc:
        logger.warning("Reddit fetch failed (%s): %s", subreddit, exc)
        return None

    if not titles:
        return None

    net = 0
    for title in titles:
        lowered = title.lower()
        net += sum(1 for w in _BULLISH_WORDS if w in lowered)
        net -= sum(1 for w in _BEARISH_WORDS if w in lowered)

    score = max(-1.0, min(1.0, net / _NORMALIZATION_CAP))
    _CACHE = (time.monotonic(), score)
    return score
