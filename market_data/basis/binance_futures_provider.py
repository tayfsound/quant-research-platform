"""Faz 344: Cross-Asset Arbitrage Engine — spot-perpetual basis verisi.

Binance'in genel, API key GEREKTİRMEYEN /fapi/v1/premiumIndex uç noktası
— tek istekte mark price (perpetual'ın gerçek işlem gördüğü fiyat),
index price (birden fazla spot borsanın kompozit referansı — kendi
spot klines'ımızdan daha güvenilir bir "adil değer" referansı, tek bir
borsaya bağımlı değil) ve son funding rate'i veriyor. CreditAgent'ın
FRED'i / VolatilityAgent'ın Deribit'i ile AYNI desen: basit, senkron,
key'siz, kısa süreli önbellekli."""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"

_CACHE: dict[str, tuple[float, dict | None]] = {}
_CACHE_TTL_SECONDS = 60


def _fetch_premium_index(symbol: str) -> dict | None:
    cached = _CACHE.get(symbol)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = httpx.get(_PREMIUM_INDEX_URL, params={"symbol": symbol}, timeout=10)
        response.raise_for_status()
        data = response.json()
        result = {
            "mark_price": float(data["markPrice"]),
            "index_price": float(data["indexPrice"]),
            "funding_rate": float(data["lastFundingRate"]),
        }
        _CACHE[symbol] = (time.monotonic(), result)
        return result
    except Exception as exc:
        logger.warning("Binance premiumIndex fetch failed (%s): %s", symbol, exc)
        _CACHE[symbol] = (time.monotonic(), None)
        return None


def fetch_perp_basis(symbol: str) -> dict | None:
    """Döner: {"basis_pct", "funding_rate", "mark_price", "index_price"}
    ya da veri çekilemezse None (fail-closed). basis_pct = (mark-index)/
    index — pozitif: perpetual primli işlem görüyor (contango, "cash-
    and-carry" fırsatı: perpetual SHORT + spot LONG)."""
    data = _fetch_premium_index(symbol)
    if data is None or data["index_price"] <= 0:
        return None
    basis_pct = (data["mark_price"] - data["index_price"]) / data["index_price"]
    return {
        "basis_pct": basis_pct,
        "funding_rate": data["funding_rate"],
        "mark_price": data["mark_price"],
        "index_price": data["index_price"],
    }
