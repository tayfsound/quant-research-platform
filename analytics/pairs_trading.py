"""Faz 200: pairs trading / istatistiksel arbitraj — gerçek, kesin tanımlı
istatistik. Engle-Granger cointegration testi elle yazılmadı, standart,
iyi test edilmiş statsmodels.tsa.stattools.coint kullanılıyor (ADF testi
üzerine kurulu, literatürde en yaygın kullanılan yöntem).

Aday çiftler bilinçli olarak sınırlı ve ekonomik olarak anlamlı: aynı
varlık sınıfı içinden, gerçekten korele olması beklenen çiftler. Kripto
ile hisse senedi eşleştirilmedi (farklı piyasa yapıları, kointegrasyon
ekonomik olarak anlamsız olurdu)."""
import numpy as np
from statsmodels.tsa.stattools import coint

PAIR_CANDIDATES: list[tuple[str, str]] = [
    ("BTCUSDT", "ETHUSDT"),  # majör kripto çifti
    # Faz 368 — GC=F/SI=F (Yahoo) yerine gerçek Binance-native karşılıkları
    # (watchlist'te zaten var, tokenize futures sözleşmeleri). ("NVDA",
    # "MSFT") çifti kaldırıldı — MSFT testnet'te yok (watchlist'ten
    # tamamen çıkarıldı), NVDA'nın (artık NVDAUSDT) tek başına eşleşecek
    # bir ikinci mega-cap teknoloji bacağı kalmadı.
    ("XAUTUSDT", "XAGUSDT"),  # altın/gümüş — klasik pairs trading çifti
]

COINTEGRATION_P_VALUE_THRESHOLD = 0.05
ZSCORE_ENTRY_THRESHOLD = 2.0


def check_cointegration(prices_a: list[float], prices_b: list[float]) -> tuple[bool, float]:
    """Engle-Granger iki-adımlı kointegrasyon testi. p_value < 0.05 ise
    iki seri gerçekten kointegre (spread'in uzun vadede sabit bir ortalamaya
    dönme eğiliminde olduğunun istatistiksel kanıtı) — icat edilmiş bir
    "korelasyon var gibi" yorumu değil."""
    if len(prices_a) != len(prices_b) or len(prices_a) < 20:
        return False, 1.0
    _, p_value, _ = coint(np.array(prices_a), np.array(prices_b))
    return bool(p_value < COINTEGRATION_P_VALUE_THRESHOLD), float(p_value)


def compute_spread_zscore(prices_a: list[float], prices_b: list[float], window: int = 20) -> float | None:
    """Spread = price_a - hedge_ratio*price_b (hedge_ratio, OLS ile
    hesaplanan gerçek regresyon katsayısı). z-score = spread'in son
    `window` barlık kendi ortalama/std'sine göre kaç standart sapma
    uzakta olduğu — standart, kesin tanımlı bir hesap."""
    if len(prices_a) != len(prices_b) or len(prices_a) < window + 1:
        return None

    a = np.array(prices_a)
    b = np.array(prices_b)

    hedge_ratio = float(np.polyfit(b, a, 1)[0])
    spread = a - hedge_ratio * b

    recent = spread[-window:]
    mean, std = recent.mean(), recent.std()
    if std == 0:
        return None
    return float((spread[-1] - mean) / std)
