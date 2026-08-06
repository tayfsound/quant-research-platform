"""Faz 224: kullanıcı bulgusu — "PNL de para birimi görünmüyor bu hangi
birimle kayıp belli değil dolar mı btc mi vs... Live predictions vs.. her
yerde aynı problem var." Sistemdeki tüm fiyat/PnL alanları zaten USD
cinsinden (kripto çiftleri USDT'ye endeksli, USDT ~ USD; hisse/endeks
zaten USD). Kullanıcı isterse BTC ya da TRY olarak görebilsin diye gerçek,
canlı dönüşüm oranları gerekiyor.

Ayrı bir FX API'sine gerek yok — Binance'in kendi gerçek piyasaları
zaten bunu sağlıyor: BTCUSDT (USD->BTC için) ve USDTTRY (USD->TRY için,
gerçek bir Binance spot çifti, doğrulandı). Bu, sistemin zaten ana veri
kaynağı olan Binance ile tutarlı — yeni bir kimlik/anahtar gerektirmiyor."""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"

# Faz 230 review önerisi: "currency_provider.py her seferinde Binance'den
# canlı oran çekiyor — kısa süreli önbellek eklenmeli." Doğru — dashboard'un
# her sayfa/görünüm değişiminde useCurrency() bunu çağırması gereksiz
# Binance isteği anlamına geliyordu. news_tone_provider.py'deki AYNI
# modül-seviyesi önbellek deseni, kur değişim hızına göre daha kısa TTL.
_CACHE: tuple | None = None
_CACHE_TTL_SECONDS = 60


def _fetch_price(symbol: str) -> float | None:
    try:
        response = httpx.get(_BINANCE_TICKER_URL, params={"symbol": symbol}, timeout=10)
        response.raise_for_status()
        return float(response.json()["price"])
    except Exception as exc:
        logger.warning("Binance ticker fetch failed (%s): %s", symbol, exc)
        return None


def fetch_currency_rates() -> dict:
    """1 USD'nin karşılığı — çarpan olarak. usd_btc: 1 USD kaç BTC eder
    (1/BTCUSDT fiyatı). usd_try: 1 USD kaç TRY eder (gerçek USDTTRY
    piyasa fiyatı, USDT~USD kabul edilerek). 60 saniye önbellekli."""
    global _CACHE
    if _CACHE and (time.monotonic() - _CACHE[0]) < _CACHE_TTL_SECONDS:
        return _CACHE[1]

    btc_usd = _fetch_price("BTCUSDT")
    usd_try = _fetch_price("USDTTRY")
    result = {
        "usd_btc": (1.0 / btc_usd) if btc_usd else None,
        "usd_try": usd_try,
    }
    _CACHE = (time.monotonic(), result)
    return result
