"""Faz 215: SentimentAgent'ın "positioning" girdisi için gerçek veri.

Önceki varsayım yanlıştı — fear_greed_provider.py'nin docstring'i
"positioning (borsa long/short oranı — genelde ücretli/karmaşık)"
diyordu, ama Binance Futures'ın global long/short hesap oranı uç noktası
(/futures/data/globalLongShortAccountRatio) gerçekten kimliksiz/ücretsiz
erişilebiliyor.

Mutlak bir eşik (ör. "ratio > 1.5 = long_bias") kullanılmadı — gerçek
veriyle ölçüldü, BTCUSDT için son 500 periyotta oran hep 1.11-1.31
aralığında (mutlak bir sayı asla "aşırı" görünmeyebilir). Bunun yerine
codebase'in zaten kullandığı desenle (realized_vol_percentile gibi)
tutarlı şekilde: oranın KENDİ yakın geçmişine göre yüzdelik dilimi
hesaplanıyor, aşırı uçlar (üst/alt %15) long_bias/short_bias sayılıyor."""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"

_CACHE: dict[str, tuple] = {}
_CACHE_TTL_SECONDS = 300


def fetch_positioning(symbol: str, period: str = "5m", limit: int = 50) -> str | None:
    cache_key = f"{symbol}:{period}"
    cached = _CACHE.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = httpx.get(
            _URL, params={"symbol": symbol, "period": period, "limit": limit}, timeout=10
        )
        response.raise_for_status()
        data = response.json()
        if not data or len(data) < 10:
            return None

        ratios = [float(d["longShortRatio"]) for d in data]
        current = ratios[-1]
        rank = sum(1 for r in ratios if r <= current) / len(ratios)

        if rank >= 0.85:
            result = "long_bias"
        elif rank <= 0.15:
            result = "short_bias"
        else:
            result = "neutral"

        _CACHE[cache_key] = (time.monotonic(), result)
        return result
    except Exception as exc:
        logger.warning("Positioning (long/short ratio) fetch failed for %s: %s", symbol, exc)
        return None
