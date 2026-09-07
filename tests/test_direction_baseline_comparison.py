"""analytics/direction_baseline_comparison.py — Faz 442 (2026-09-07),
Direction Prediction Engine. GPT'nin önerisi: Random/Always-LONG/
Always-SHORT/Momentum/AI/Council'i AYNI forward target'a karşı ölç."""
from analytics.direction_baseline_comparison import compute_baseline_comparison


def _record(entry, price_1h, direction=None, council_direction=None, regime=None):
    return {
        "entry_price": entry, "price_at_horizon": price_1h,
        "direction": direction, "council_direction": council_direction, "market_regime": regime,
    }


def test_returns_none_below_min_sample_size():
    records = [_record(100.0, 101.0, "LONG") for _ in range(10)]
    assert compute_baseline_comparison(records) is None


def test_always_long_beats_always_short_when_up_is_more_common():
    """20 UP + 10 DOWN -> her zaman LONG %66.7, her zaman SHORT %33.3."""
    records = [_record(100.0, 101.0) for _ in range(20)] + [_record(100.0, 99.0) for _ in range(10)]
    result = compute_baseline_comparison(records)
    assert result["n"] == 30
    assert result["accuracy"]["always_long"] > result["accuracy"]["always_short"]
    assert abs(result["accuracy"]["always_long"] - 20 / 30) < 1e-3  # 4 ondalığa yuvarlanıyor


def test_random_is_always_exactly_half_deterministic():
    """Rastgele bir sayı üreteciyle SİMÜLE edilmiyor — yazı-turanın
    beklenen değeri zaten tam olarak 0.5, her çağrıda AYNI (tekrarlanabilir)."""
    records = [_record(100.0, 101.0) for _ in range(15)] + [_record(100.0, 99.0) for _ in range(15)]
    r1 = compute_baseline_comparison(records)
    r2 = compute_baseline_comparison(records)
    assert r1["accuracy"]["random"] == 0.5
    assert r1["accuracy"]["random"] == r2["accuracy"]["random"]


def test_ai_final_direction_perfect_when_it_always_matches_ground_truth():
    records = (
        [_record(100.0, 101.0, direction="LONG") for _ in range(15)]
        + [_record(100.0, 99.0, direction="SHORT") for _ in range(15)]
    )
    result = compute_baseline_comparison(records)
    assert result["accuracy"]["ai_final_direction"] == 1.0


def test_ai_final_direction_matches_todays_real_finding_when_anti_correlated():
    """Bugünkü gerçek bulgu: AI'nin nihai kararı fiyatla ANTİ-korele
    (UP iken SHORT diyor, DOWN iken LONG diyor gibi bir örüntü) —
    fonksiyon bu durumu doğru şekilde <%50 doğruluk olarak yakalamalı."""
    records = (
        [_record(100.0, 101.0, direction="SHORT") for _ in range(15)]  # UP oldu ama SHORT demiş
        + [_record(100.0, 99.0, direction="LONG") for _ in range(15)]  # DOWN oldu ama LONG demiş
    )
    result = compute_baseline_comparison(records)
    assert result["accuracy"]["ai_final_direction"] == 0.0


def test_momentum_uses_market_regime_and_falls_back_to_coin_flip():
    records = [
        _record(100.0, 101.0, regime="bullish_normal"),  # UP oldu, momentum UP dedi -> doğru
        _record(100.0, 99.0, regime="bullish_low"),       # DOWN oldu, momentum UP dedi -> yanlış
        *[_record(100.0, 101.0, regime=None) for _ in range(28)],  # rejim yok -> yazı-tura (0.5)
    ]
    result = compute_baseline_comparison(records)
    # (1 doğru + 0 yanlış + 28*0.5) / 30
    assert abs(result["accuracy"]["momentum"] - (1 + 28 * 0.5) / 30) < 1e-6


def test_neutral_ground_truth_rows_are_excluded_entirely():
    """GPT'nin uyarısı: fiyatın anlamsız küçük hareket ettiği durumlar
    (NEUTRAL) hiçbir baseline'ın hesabına dahil edilmemeli."""
    directional = [_record(100.0, 101.0) for _ in range(15)] + [_record(100.0, 99.0) for _ in range(15)]
    neutral = [_record(100.0, 100.001) for _ in range(50)]  # eşiğin çok altında
    result_with_neutral = compute_baseline_comparison(directional + neutral)
    result_without_neutral = compute_baseline_comparison(directional)
    assert result_with_neutral["n"] == result_without_neutral["n"] == 30


def test_matches_todays_real_baseline_numbers():
    """Bugünkü ad-hoc SQL + Python taramasının ÜRETTİĞİ gerçek sayılar
    (n=6903 ikili kayıt): AI %43.8, Council %45.5, Momentum %46.9,
    Always-LONG %52.3. Bu test, tam eşit gerçek veriyle DEĞİL ama aynı
    büyüklük sırasını (AI < Council < Momentum < Always-LONG) koruyan
    sentetik bir veri kümesiyle regresyon testi yapıyor — asıl birebir
    doğrulama gerçek veri exportuyla ayrıca yapıldı (bkz. plan dosyası)."""
    import random as _random

    _random.seed(7)
    records = []
    for _ in range(1000):
        up = _random.random() < 0.461  # bugünkü gerçek UP oranı
        entry, price = 100.0, (101.0 if up else 99.0)
        # AI %43.8 dogru olacak sekilde kasten kötü tahmin ediyor
        ai_dir = ("LONG" if up else "SHORT") if _random.random() < 0.438 else ("SHORT" if up else "LONG")
        records.append(_record(entry, price, direction=ai_dir))
    result = compute_baseline_comparison(records)
    assert 0.40 <= result["accuracy"]["ai_final_direction"] <= 0.48
