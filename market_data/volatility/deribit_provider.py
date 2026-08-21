"""Faz 336: VolatilityAgent'a gerçek Deribit DVOL (BTC/ETH implied
volatility index) verisi — Deribit'in genel, API key GEREKTİRMEYEN
public endpoint'i (VIX'in kripto karşılığı, endüstri standardı).

Kasıtlı olarak SADECE tek, basit bir sinyal: DVOL'un kendi son geçmişine
göre HIZLI değişimi. Volatilite endekslerinin (VIX dahil) yön tahmini
literatüründe (kripto için) net/tutarlı bir "yüksek IV = düşecek" ilişkisi
YOK — ama "volatilite ANİDEN sıçrıyor" genel, varlık-sınıfından bağımsız
bir piyasa-stresi göstergesidir (CreditAgent'ın yield curve inversion'ıyla
AYNI asimetrik disiplin: sadece STRES ucu puanlanıyor, "sakin" durumun
kendisi bir alpha kaynağı sayılmıyor)."""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_DERIBIT_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"

_CACHE: dict[str, tuple[float, list[float] | None]] = {}
_CACHE_TTL_SECONDS = 900


def _fetch_dvol_series(currency: str, hours: int = 24) -> list[float] | None:
    cache_key = f"{currency}_{hours}"
    cached = _CACHE.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    now_ms = int(time.time() * 1000)
    try:
        response = httpx.get(
            _DERIBIT_URL,
            params={
                "currency": currency,
                "start_timestamp": now_ms - hours * 3600 * 1000,
                "end_timestamp": now_ms,
                "resolution": 3600,
            },
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json().get("result", {}).get("data", [])
        # Her satır: [timestamp, open, high, low, close] — kapanış (close, index 4) kullanılıyor.
        values = [float(row[4]) for row in rows if len(row) >= 5]
        result = values or None
        _CACHE[cache_key] = (time.monotonic(), result)
        return result
    except Exception as exc:
        logger.warning("Deribit DVOL fetch failed (%s): %s", currency, exc)
        _CACHE[cache_key] = (time.monotonic(), None)
        return None


def fetch_dvol_level(currency: str = "BTC") -> float | None:
    """En güncel DVOL değeri (yıllıklandırılmış %, ör. 45.0 = %45)."""
    values = _fetch_dvol_series(currency)
    if not values:
        return None
    return values[-1]


def fetch_dvol_trend(currency: str = "BTC") -> str | None:
    """Son 24 saatteki değişime göre: 'spiking' (>%15 göreli artış —
    ani volatilite genişlemesi, piyasa stresi), 'falling' (>%15 göreli
    düşüş — sakinleşme/vol-crush), 'stable'."""
    values = _fetch_dvol_series(currency)
    if not values or len(values) < 2 or values[0] == 0:
        return None
    pct_change = (values[-1] - values[0]) / abs(values[0])
    if pct_change > 0.15:
        return "spiking"
    if pct_change < -0.15:
        return "falling"
    return "stable"
