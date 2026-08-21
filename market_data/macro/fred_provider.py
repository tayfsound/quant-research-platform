"""Faz 197: MacroAgent'a gerçek FRED (Federal Reserve Economic Data)
verisi — 4 gerçek, resmi, kesin tanımlı seri:
- CPIAUCSL (Tüketici Fiyat Endeksi) -> inflation_trend
- UNRATE (İşsizlik oranı) -> employment_trend
- FEDFUNDS (Fed fon oranı) -> central_bank_bias
- M2SL (M2 para arzı) -> liquidity_condition

Her biri son `lookback` gözlemdeki gerçek değişime göre (icat edilmiş bir
"görüş" değil, dümdüz sayı farkı) rising/falling/stable gibi kategorik bir
etikete çevriliyor. Eşikler gelişigüzel ama makul yuvarlak sayılar — sahte
bir kesinlik iddiası yok."""
import logging
import time

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# Makro veri günlük/aylık değişir — her watchlist sembolü için ayrı ayrı
# FRED'i çağırmak (10 sembol x 4 seri = her cycle'da 40 gereksiz istek)
# hem yavaş hem anlamsız. Süreç-içi, kısa ömürlü bir önbellek yeterli.
_CACHE: dict[str, tuple[float, list[float] | None]] = {}
_CACHE_TTL_SECONDS = 3600


def _fetch_series(series_id: str, limit: int = 4) -> list[float] | None:
    cached = _CACHE.get(series_id)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    settings = get_settings()
    if not settings.FRED_API_KEY:
        return None
    try:
        response = httpx.get(
            _FRED_URL,
            params={
                "series_id": series_id,
                "api_key": settings.FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=10,
        )
        response.raise_for_status()
        observations = response.json().get("observations", [])
        values = [float(o["value"]) for o in observations if o.get("value") not in (None, ".", "")]
        result = values or None
        _CACHE[series_id] = (time.monotonic(), result)
        return result
    except Exception as exc:
        logger.warning("FRED fetch failed (%s): %s", series_id, exc)
        return None


def fetch_inflation_trend() -> str | None:
    values = _fetch_series("CPIAUCSL")
    if not values or len(values) < 2 or values[-1] == 0:
        return None
    pct_change = (values[0] - values[-1]) / abs(values[-1])
    if pct_change > 0.003:
        return "rising"
    if pct_change < -0.003:
        return "falling"
    return "stable"


def fetch_employment_trend() -> str | None:
    values = _fetch_series("UNRATE")
    if not values or len(values) < 2:
        return None
    point_change = values[0] - values[-1]  # işsizlik oranı yükseldi mi?
    if point_change > 0.1:
        return "weakening"
    if point_change < -0.1:
        return "improving"
    return "stable"


def fetch_central_bank_bias() -> str | None:
    values = _fetch_series("FEDFUNDS")
    if not values or len(values) < 2:
        return None
    point_change = values[0] - values[-1]
    if point_change > 0.1:
        return "hawkish"
    if point_change < -0.1:
        return "dovish"
    return "neutral"


def fetch_liquidity_condition() -> str | None:
    values = _fetch_series("M2SL")
    if not values or len(values) < 2 or values[-1] == 0:
        return None
    pct_change = (values[0] - values[-1]) / abs(values[-1])
    if pct_change > 0.005:
        return "loose"
    if pct_change < -0.005:
        return "tight"
    return "neutral"


def fetch_net_liquidity_trend() -> str | None:
    """Faz 267 — kullanıcı bulgusu: "devletler borçlarını dört yıllık
    dönemlerle öder, bu döngü tamamlanınca piyasaya likidite girer."
    liquidity_condition (M2SL, aylık, yavaş) bu döngüyü yakalayamıyor.
    Gerçek, makro analistlerin ("net liquidity") kullandığı standart
    formül — haftalık/günlük, çok daha hızlı hareket eden üç GERÇEK
    FRED serisinden:
    - WALCL: Fed'in toplam bilançosu (milyon $, haftalık)
    - WTREGEN: Hazine'nin Fed'deki nakit hesabı — TGA (milyon $, haftalık).
      Borç tavanı çözülüp Hazine yeniden borçlanmaya başlayınca bu hesap
      hızla dolar (piyasadan likidite çeker); Hazine harcama yaparken
      boşalır (piyasaya likidite geri döner) — kullanıcının tarif ettiği
      döngünün doğrudan karşılığı.
    - RRPONTSYD: Fed'in gecelik ters repo tesisi (milyar $, günlük) —
      bankaların/fonların Fed'e "park ettiği" (piyasada OLMAYAN) para.
    Net Likidite = WALCL - WTREGEN - (RRPONTSYD * 1000, birim milyona
    çevriliyor). Yükseliyorsa risk varlıkları için tarihsel olarak
    destekleyici (expanding); düşüyorsa kısıtlayıcı (contracting)."""
    walcl = _fetch_series("WALCL", limit=8)
    tga = _fetch_series("WTREGEN", limit=8)
    rrp = _fetch_series("RRPONTSYD", limit=8)
    if not walcl or not tga or not rrp:
        return None

    n = min(len(walcl), len(tga), len(rrp))
    if n < 2:
        return None

    net_liquidity = [walcl[i] - tga[i] - rrp[i] * 1000 for i in range(n)]
    if net_liquidity[-1] == 0:
        return None

    pct_change = (net_liquidity[0] - net_liquidity[-1]) / abs(net_liquidity[-1])
    if pct_change > 0.01:
        return "expanding"
    if pct_change < -0.01:
        return "contracting"
    return "stable"


# Faz 333 — CreditAgent, kullanıcı isteği (harici bir AI incelemesinin
# önerdiği, kullanıcının onayladığı ilk yeni ajan): "credit leads equity"
# — tahvil piyasası, hisse/kripto gibi risk varlıklarından ÖNCE sinyal
# verir. İki GERÇEK, resmi, kesin tanımlı FRED serisi (MacroAgent'ın
# kullandığı AYNI desen — icat edilmiş bir "görüş" değil, dümdüz sayı
# farkı):
# - T10Y2Y: 10 yıllık - 2 yıllık Hazine tahvili getiri farkı ("yield
#   curve"). Negatif (tersine dönmüş eğri) tarihsel olarak güçlü bir
#   resesyon uyarı sinyali — gecikmeli ama son 50+ yılda hiç yanlış
#   pozitif vermemiş, en köklü makro göstergelerden biri.
# - BAMLH0A0HYM2 (ICE BofA ABD Yüksek Getirili Endeks OAS): yüksek
#   getirili tahvil spread'i. Genişliyorsa piyasa kredi riskini daha
#   pahalı fiyatlıyor demek — risk-off, kripto gibi risk varlıkları için
#   tarihsel olarak olumsuz. Daralıyorsa risk-on.
def fetch_yield_curve_signal() -> str | None:
    values = _fetch_series("T10Y2Y", limit=2)
    if not values:
        return None
    if values[0] < 0:
        return "inverted"
    return "normal"


def fetch_credit_spread_trend() -> str | None:
    values = _fetch_series("BAMLH0A0HYM2", limit=4)
    if not values or len(values) < 2:
        return None
    point_change = values[0] - values[-1]  # yüzde puan (ör. %2.75 -> 2.75)
    if point_change > 0.2:
        return "widening"
    if point_change < -0.2:
        return "narrowing"
    return "stable"
