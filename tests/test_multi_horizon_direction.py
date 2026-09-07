"""analytics/multi_horizon_direction.py — Faz 444 (2026-09-07), Direction
Prediction Engine, GPT'nin 4 numaralı önceliği: 15m/1h/4h yönünü AYRI
AYRI ölçüp uyuşmazlığı raporlamak."""
from analytics.multi_horizon_direction import compute_disagreement_rate, label_multi_horizon


def test_all_horizons_agree_when_price_keeps_rising():
    result = label_multi_horizon(100.0, {"15m": 100.2, "1h": 101.0, "4h": 103.0})
    assert result["labels"]["15m"] == "UP"
    assert result["labels"]["1h"] == "UP"
    assert result["labels"]["4h"] == "UP"
    assert result["all_agree"] is True
    assert result["disagreement"] is False


def test_disagreement_when_short_term_pullback_inside_a_longer_uptrend():
    """GPT'nin tam örneği: 15m DOWN, 1h/4h UP -- kısa vadeli geri
    çekilme, ana trend yukarı."""
    result = label_multi_horizon(100.0, {"15m": 99.5, "1h": 101.0, "4h": 103.0})
    assert result["labels"]["15m"] == "DOWN"
    assert result["labels"]["1h"] == "UP"
    assert result["labels"]["4h"] == "UP"
    assert result["all_agree"] is False
    assert result["disagreement"] is True


def test_all_agree_is_none_when_fewer_than_two_horizons_are_directional():
    """Sadece 1 ufuk yön veriyorsa (digerleri NEUTRAL/veri yok)
    'anlaşıyorlar mı' sorusu anlamsız -- None, icat edilmiş bir cevap yok."""
    result = label_multi_horizon(100.0, {"15m": 100.2, "1h": None, "4h": 100.01})
    assert result["all_agree"] is None
    assert result["disagreement"] is False


def test_compute_disagreement_rate_counts_real_examples():
    records = (
        [{"entry_price": 100.0, "price_15m": 100.2, "price_1h": 101.0, "price_4h": 103.0} for _ in range(7)]  # anlaşıyor
        + [{"entry_price": 100.0, "price_15m": 99.5, "price_1h": 101.0, "price_4h": 103.0} for _ in range(3)]  # anlaşmıyor
    )
    result = compute_disagreement_rate(records)
    assert result["n_comparable"] == 10
    assert result["n_disagreements"] == 3
    assert result["disagreement_rate"] == 0.3
    assert len(result["example_disagreements"]) == 3


def test_compute_disagreement_rate_returns_none_below_min_sample_size():
    records = [{"entry_price": 100.0, "price_15m": 99.5, "price_1h": 101.0, "price_4h": 103.0} for _ in range(5)]
    assert compute_disagreement_rate(records) is None
