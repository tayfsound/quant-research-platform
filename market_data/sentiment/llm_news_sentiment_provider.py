"""Faz 268-sonrası — kullanıcı isteği: Reddit sentiment kapanmıştı (Devvit
politikası AI kullanımını yasaklıyor, bkz. reddit_provider.py'nin
docstring'i) — "LLM'i kullanarak gerçek haberleri tarayıp özetleyelim,
Reddit yerine bunu koyalım" fikrinin gerçek uygulaması.

news_tone_provider.py'nin ZATEN kullandığı gerçek, ücretsiz, kimliksiz
RSS akışlarından (CoinDesk + CoinTelegraph) gerçek başlıklar çekilip
NvidiaDecisionCritic'e (llm_reasoner.py) veriliyor — model kendi eğitim
verisinden "haber uyduruyor" DEĞİL, burada VERİLEN gerçek, güncel
başlıkları özetliyor/puanlıyor. Basit anahtar-kelime sayımından
(news_tone_provider.py) farkı: gerçek bağlamsal okuma (ör. "X düştü ama
analistler bunu sağlıklı bir düzeltme olarak görüyor" gibi nüansları
kelime sayımı yakalayamaz).

Mimari not — KASITLI OLARAK iki fonksiyona bölündü:
- get_cached(): SADECE önbelleği okur, hiçbir zaman LLM çağırmaz, anlık —
  services/context_adapter.py (HER karar cycle'ında çalışır) bunu çağırır.
- refresh(): gerçek işi yapar (RSS + ~90s'ye kadar sürebilen gerçek LLM
  çağrısı) — SADECE ayrı, periyodik bir Celery görevinden (bkz. services/
  tasks.py) çağrılmalı. Bu ayrım olmadan, canlı karar döngüsü her
  cache-miss'te ~90 saniye bloke olurdu."""
import json
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

_RSS_FEEDS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
)

_CACHE: tuple | None = None  # (monotonic_ts, score, summary, headline_count)
_CACHE_TTL_SECONDS = 1800  # 30dk — gerçek haber akışı bu kadar sık değişmiyor,
# ve her tazeleme gerçek bir (~90s'ye kadar) LLM çağrısı.

_SYSTEM_PROMPT = """ÖNEMLİ: Bütün yanıtını SADECE TÜRKÇE yaz.

Sana gerçek, güncel kripto para haberi başlıkları verilecek. Bu başlıkları
oku ve genel piyasa duyarlılığını değerlendir.
Kurallar:
- SADECE sana verilen başlıklara dayan — kendi bilgin/hafızandan haber
  UYDURMA, verilmeyen bir olaydan bahsetme.
- sentiment_score: -1.0 (çok negatif/bearish) ile +1.0 (çok pozitif/
  bullish) arasında, ondalıklı bir sayı. Karışık/nötr haberler 0'a yakın olmalı.
- summary: 2-4 cümlelik, Türkçe, genel piyasa havasını özetleyen bir metin.
- Output SADECE geçerli JSON:
{"sentiment_score": 0.15, "summary": "(Türkçe özet)"}
"""


def _fetch_real_headlines(limit_per_feed: int = 15) -> list[str]:
    headlines: list[str] = []
    for url in _RSS_FEEDS:
        try:
            response = httpx.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()
            titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", response.text)
            # İlk <title> genelde feed'in kendi adı — gerçek haber başlığı değil.
            headlines.extend(t.strip() for t in titles[1:limit_per_feed + 1] if t.strip())
        except Exception as exc:
            logger.warning("RSS fetch failed (%s): %s", url, exc)
    return headlines


def get_cached() -> tuple[float | None, str | None]:
    """SADECE önbelleği okur — hiçbir zaman ağ/LLM çağrısı yapmaz, anlık
    döner. Hiç tazelenmemişse ya da önbellek süresi dolmuşsa (None, None)
    — fail-closed, uydurulmuş bir skor/özet asla döndürülmez."""
    if _CACHE is None:
        return None, None
    ts, score, summary, _ = _CACHE
    if (time.monotonic() - ts) >= _CACHE_TTL_SECONDS:
        return None, None
    return score, summary


def refresh() -> tuple[float | None, str | None]:
    """Gerçek işi yapan yavaş fonksiyon (RSS + LLM çağrısı, ~90s'ye kadar
    sürebilir) — SADECE periyodik bir Celery görevinden çağrılmalı, canlı
    karar döngüsünden DEĞİL. NVIDIA_API_KEY boşsa ya da RSS/LLM
    başarısız olursa (None, None) döner, önbellek GÜNCELLENMEZ (eski,
    hâlâ geçerli bir önbellek varsa o korunur — bir başarısızlık, çalışan
    bir sinyali silmemeli)."""
    global _CACHE
    import asyncio

    from config.settings import get_settings

    if not get_settings().NVIDIA_API_KEY:
        return None, None

    headlines = _fetch_real_headlines()
    if not headlines:
        logger.warning("LLM news sentiment: no real headlines fetched, skipping")
        return None, None

    from llm_reasoner import NvidiaDecisionCritic

    critic = NvidiaDecisionCritic()
    user_message = "Gerçek, güncel kripto haber başlıkları:\n" + "\n".join(f"- {h}" for h in headlines)

    try:
        raw = asyncio.run(critic.ask(user_message, timeout_ms=120000, system_prompt=_SYSTEM_PROMPT))
        start = raw.find("{")
        data = json.loads(raw[start:]) if start != -1 else {}
        score = float(data.get("sentiment_score", 0.0))
        score = max(-1.0, min(1.0, score))
        summary = str(data.get("summary", "")).strip()
        if not summary:
            return None, None
    except Exception as exc:
        logger.warning("LLM news sentiment analysis failed: %s", exc)
        return None, None

    _CACHE = (time.monotonic(), score, summary, len(headlines))
    return score, summary
