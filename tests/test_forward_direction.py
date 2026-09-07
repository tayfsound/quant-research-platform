"""analytics/forward_direction.py — Faz 441 (2026-09-07), Direction
Prediction Engine. Bkz. ~/.claude/plans/velvety-whistling-parasol.md.
Kullanıcı + GPT teşhisi: sistem "trade kazandı mı" (outcome) ile "fiyat
hangi yöne gitti" (direction) hedeflerini karıştırıyor — bu fonksiyon
ikincisini, birincisinden TAMAMEN bağımsız ölçüyor."""
from analytics.forward_direction import label_forward_direction


def test_up_when_forward_return_exceeds_threshold():
    assert label_forward_direction(100.0, 100.1, threshold_pct=0.0005) == "UP"


def test_down_when_forward_return_below_negative_threshold():
    assert label_forward_direction(100.0, 99.9, threshold_pct=0.0005) == "DOWN"


def test_neutral_when_forward_return_is_within_the_noise_band():
    """GPT'nin uyarısı: +0.05%/-0.08%/+0.11% gibi anlamsız küçük
    hareketlere zorla LONG/SHORT etiketi vermek gürültü öğretir."""
    assert label_forward_direction(100.0, 100.02, threshold_pct=0.0005) == "NEUTRAL"
    assert label_forward_direction(100.0, 99.98, threshold_pct=0.0005) == "NEUTRAL"


def test_boundary_values_are_neutral_not_up_or_down():
    """Eşiğe TAM eşit bir hareket "aşmadı" sayılmalı (> ve < katı,
    >= /<= değil) — sınırda icat edilmiş bir yön verilmemeli."""
    assert label_forward_direction(100.0, 100.05, threshold_pct=0.0005) == "NEUTRAL"


def test_none_when_entry_price_is_missing_or_non_positive():
    assert label_forward_direction(None, 100.0) is None
    assert label_forward_direction(0.0, 100.0) is None
    assert label_forward_direction(-5.0, 100.0) is None


def test_none_when_price_at_horizon_is_missing():
    """Ufuktaki fiyat bulunamadıysa (veri yok) fail-closed None —
    icat edilmiş bir etiket asla üretilmez."""
    assert label_forward_direction(100.0, None) is None


def test_matches_todays_real_1h_forward_baseline_example():
    """Bugün elle bulunan gerçek bir örnek: BTC entry~79000, 1sa sonra
    ~78900 -> %0.05 eşiğiyle DOWN (bugünkü baseline karşılaştırmasının
    aynı eşiğiyle üretilen sınıf)."""
    assert label_forward_direction(79000.0, 78900.0, threshold_pct=0.0005) == "DOWN"
