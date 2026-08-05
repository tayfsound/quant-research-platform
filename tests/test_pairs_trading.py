"""Faz 200: pairs trading — gerçek Engle-Granger cointegration testi
(statsmodels) + spread z-score. Sentetik ama kontrollü seriler kullanıyor
(gerçek kointegre/kointegre-olmayan davranışı garanti etmek için)."""
import numpy as np

from analytics.pairs_trading import check_cointegration, compute_spread_zscore


def _cointegrated_series(n=100, seed=1):
    """Ortak bir stokastik trend paylaşan, gerçekten kointegre iki seri
    (klasik simülasyon: B = A + durağan gürültü)."""
    rng = np.random.RandomState(seed)
    common_trend = np.cumsum(rng.normal(0, 1, n)) + 100
    noise = rng.normal(0, 0.5, n)
    a = common_trend
    b = common_trend + noise
    return a.tolist(), b.tolist()


def _independent_series(n=100, seed=1):
    """İki bağımsız random walk — kointegre OLMAMALI."""
    rng = np.random.RandomState(seed)
    a = np.cumsum(rng.normal(0, 1, n)) + 100
    b = np.cumsum(rng.normal(0, 1, n)) + 200
    return a.tolist(), b.tolist()


def test_cointegrated_series_are_detected_as_cointegrated():
    a, b = _cointegrated_series()
    is_coint, p_value = check_cointegration(a, b)
    assert is_coint is True
    assert p_value < 0.05


def test_independent_random_walks_are_not_cointegrated():
    a, b = _independent_series(seed=42)
    is_coint, p_value = check_cointegration(a, b)
    assert is_coint is False


def test_too_few_points_returns_not_cointegrated():
    is_coint, p_value = check_cointegration([1.0] * 5, [1.0] * 5)
    assert is_coint is False
    assert p_value == 1.0


def test_spread_zscore_is_extreme_after_a_sudden_divergence():
    a, b = _cointegrated_series(n=100, seed=2)
    # Son barda A'yı aniden çok yükselt — spread aşırı sapmalı.
    a[-1] = a[-1] + 20
    z = compute_spread_zscore(a, b)
    assert z is not None
    assert abs(z) > 2.0


def test_spread_zscore_is_small_for_a_stable_cointegrated_pair():
    a, b = _cointegrated_series(n=100, seed=3)
    z = compute_spread_zscore(a, b)
    assert z is not None
    assert abs(z) < 3.0  # tipik durağan davranış, aşırı bir sapma yok


def test_spread_zscore_none_with_insufficient_history():
    assert compute_spread_zscore([1.0, 2.0], [1.0, 2.0]) is None
