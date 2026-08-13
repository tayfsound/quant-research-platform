"""Data Quality Scoring — fiyat spike/wick manipülasyonu tespiti."""
from datetime import UTC, datetime, timedelta

from market_data.features.signal_engine import compute_data_quality_score
from market_data.ingestion.ohlcv import OHLCV


def _bar(t: int, open_: float, high: float, low: float, close: float, volume: float = 100.0) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=t),
        open=open_, high=high, low=low, close=close, volume=volume,
    )


def _clean_bars(n: int, base: float = 100.0) -> list[OHLCV]:
    return [_bar(i, base, base * 1.002, base * 0.998, base) for i in range(n)]


def test_clean_stable_series_has_a_perfect_score():
    bars = _clean_bars(30)
    result = compute_data_quality_score(bars)
    assert result["data_quality_score"] == 1.0
    assert result["anomaly_count"] == 0


def test_too_few_bars_is_honestly_assumed_clean_fail_open():
    bars = _clean_bars(3)
    result = compute_data_quality_score(bars)
    assert result["data_quality_score"] == 1.0
    assert result["anomaly_count"] == 0


def test_high_less_than_low_is_a_hard_anomaly():
    bars = _clean_bars(10)
    bars[5] = _bar(5, 100.0, 99.0, 101.0, 100.0)  # high < low
    result = compute_data_quality_score(bars)
    assert result["anomaly_count"] == 1
    assert "high < low" in result["anomalies"][0]


def test_close_outside_high_low_range_is_a_hard_anomaly():
    bars = _clean_bars(10)
    bars[5] = _bar(5, 100.0, 101.0, 99.0, 150.0)  # close way above high
    result = compute_data_quality_score(bars)
    assert result["anomaly_count"] == 1


def test_a_wick_that_immediately_reverts_is_flagged_as_a_bad_print():
    """Klasik kötü print imzası: uzun bir alt fitil (gövdenin 4x'inden
    fazlası, bar aralığının %60'ından fazlası) ama BİR SONRAKİ bar
    fiyatı sanki hiç oraya gitmemiş gibi neredeyse tam eski yerine
    dönüyor — gerçek bir hareketin devamı yok."""
    bars = _clean_bars(20, base=100.0)
    # bar 10: alt fitille 100 -> 70'e iniyor, küçük ama sıfır olmayan gövde
    bars[10] = _bar(10, 99.6, 100.0, 70.0, 99.5)
    # bar 11: fiyat neredeyse tam eski (99.5) seviyesine dönüyor -> tersine dönüş
    bars[11] = _bar(11, 99.5, 100.0, 99.0, 99.4)

    result = compute_data_quality_score(bars)
    assert result["anomaly_count"] == 1
    assert "kötü print şüphesi" in result["anomalies"][0]
    assert result["data_quality_score"] < 1.0


def test_a_wick_with_real_follow_through_is_not_flagged():
    """AYNI büyüklükte bir fitil ama bir sonraki bar fiyatı DÜŞÜK
    seviyede tutuyor (gerçek bir hareketin devamı) — bu bir manipülasyon/
    kötü print değil, gerçek bir fiyat hareketi, flag edilmemeli."""
    bars = _clean_bars(20, base=100.0)
    bars[10] = _bar(10, 99.6, 100.0, 70.0, 99.5)
    bars[11] = _bar(11, 75.0, 78.0, 72.0, 76.0)  # düşük seviyede kalıyor, gerçek devam

    result = compute_data_quality_score(bars)
    assert result["anomaly_count"] == 0
    assert result["data_quality_score"] == 1.0


def test_negative_volume_is_flagged():
    bars = _clean_bars(10)
    bars[3] = _bar(3, 100.0, 100.2, 99.8, 100.0, volume=-5.0)
    result = compute_data_quality_score(bars)
    assert result["anomaly_count"] == 1
    assert "negatif hacim" in result["anomalies"][0]


def test_score_reflects_the_proportion_of_anomalous_bars():
    bars = _clean_bars(10)
    bars[2] = _bar(2, 100.0, 99.0, 101.0, 100.0)  # high < low
    bars[7] = _bar(7, 100.0, 99.0, 101.0, 100.0)  # high < low
    result = compute_data_quality_score(bars)
    assert result["anomaly_count"] == 2
    assert abs(result["data_quality_score"] - 0.8) < 1e-6
