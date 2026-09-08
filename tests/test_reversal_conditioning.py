"""Faz 459 — analytics/reversal_conditioning.py birim testleri.

Testlerin tamamı TEK bir soruyu farklı açılardan sınıyor: dönüş etkisi
sabit tutulduğunda Council'in yön çıktısı bir fark yaratıyor mu? Üç
sonucun (doğru işaret / ters işaret / hiç bilgi yok) her biri ayrı ayrı
üretilip doğru teşhis edildiği doğrulanıyor -- çünkü bu üçü taban tabana
zıt mimari kararlar doğuruyor.
"""
import math

from analytics.reversal_conditioning import (
    bucket_prior_return,
    compute_conditional_direction_value,
)


def _rec(direction, forward_label, prior_return, count):
    return [{
        "direction": direction, "forward_label": forward_label,
        "prior_return": prior_return,
    }] * count


def test_bucket_prior_return_thresholds():
    assert bucket_prior_return(0.005) == "PRIOR_UP"
    assert bucket_prior_return(-0.005) == "PRIOR_DOWN"
    assert bucket_prior_return(0.0) == "PRIOR_FLAT"
    assert bucket_prior_return(0.0005) == "PRIOR_FLAT"  # esigin altinda


def test_bucket_prior_return_fails_closed_on_missing_data():
    """Eksik veri -> None; uydurma bir tabaka ASLA üretilmez."""
    assert bucket_prior_return(None) is None


def test_detects_a_genuinely_informative_council():
    """Council doğru işaretli gerçek bilgi taşıyorsa: her tabakada
    LONG dediğinde yükseliş olasılığı SHORT dediğinden yüksek."""
    records = []
    for prior, base in ((-0.005, 0.60), (0.0, 0.50), (0.005, 0.40)):
        # LONG dedigi yerlerde +15pp, SHORT dedigi yerlerde -15pp.
        records += _rec("LONG", "UP", prior, round((base + 0.15) * 400))
        records += _rec("LONG", "DOWN", prior, 400 - round((base + 0.15) * 400))
        records += _rec("SHORT", "UP", prior, round((base - 0.15) * 400))
        records += _rec("SHORT", "DOWN", prior, 400 - round((base - 0.15) * 400))

    result = compute_conditional_direction_value(records)

    assert result["verdict"] == "signal_correct_sign"
    assert math.isclose(result["pooled_separation"], 0.30, abs_tol=0.01)


def test_detects_an_inverted_council_signal():
    """Bilgi VAR ama işareti ters -- kurtarılabilir durum. Faz 458'in
    negatif beceri bulgusunun bu açıklaması doğruysa buraya düşeriz."""
    records = []
    for prior, base in ((-0.005, 0.60), (0.0, 0.50), (0.005, 0.40)):
        records += _rec("LONG", "UP", prior, round((base - 0.12) * 400))
        records += _rec("LONG", "DOWN", prior, 400 - round((base - 0.12) * 400))
        records += _rec("SHORT", "UP", prior, round((base + 0.12) * 400))
        records += _rec("SHORT", "DOWN", prior, 400 - round((base + 0.12) * 400))

    result = compute_conditional_direction_value(records)

    assert result["verdict"] == "signal_inverted"
    assert result["pooled_separation"] < -0.02


def test_detects_a_council_that_only_reproduces_the_reversal_effect():
    """EN KRİTİK SENARYO: güçlü bir dönüş etkisi VAR, negatif ham beceri
    de VAR -- ama Council'in kendi katkısı SIFIR. Tabaka içinde LONG ile
    SHORT'un ileri yükseliş olasılığı AYNI.

    Bu durumda Council'i "düzeltmenin" hiçbir anlamı yoktur; sinyali ters
    çevirmek de işe yaramaz (çevirecek bilgi yok). Doğru hamle Council'in
    yerine doğrudan bir dönüş katmanı koymaktır."""
    records = []
    for prior, base in ((-0.005, 0.65), (0.0, 0.50), (0.005, 0.42)):
        for direction in ("LONG", "SHORT"):
            records += _rec(direction, "UP", prior, round(base * 400))
            records += _rec(direction, "DOWN", prior, 400 - round(base * 400))

    result = compute_conditional_direction_value(records)

    assert result["verdict"] == "no_incremental_information"
    assert math.isclose(result["pooled_separation"], 0.0, abs_tol=1e-6)
    # Donus etkisinin kendisi GERCEK ve guclu: onceki dusus sonrasi
    # yukselis olasiligi %65, onceki yukselis sonrasi %42.
    assert math.isclose(result["reversal_effect"], 0.23, abs_tol=0.01)


def test_reversal_effect_is_measured_independently_of_the_council():
    """Dönüş etkisi, Council'in ne dediğinden bağımsız olarak, saf
    bağlam bilgisi olarak raporlanmalı -- "hangisi daha çok bilgi
    taşıyor" karşılaştırması ancak böyle yapılabilir."""
    records = []
    records += _rec("LONG", "UP", -0.005, 300) + _rec("LONG", "DOWN", -0.005, 100)
    records += _rec("SHORT", "UP", -0.005, 150) + _rec("SHORT", "DOWN", -0.005, 50)
    records += _rec("LONG", "UP", 0.005, 100) + _rec("LONG", "DOWN", 0.005, 300)
    records += _rec("SHORT", "UP", 0.005, 50) + _rec("SHORT", "DOWN", 0.005, 150)

    result = compute_conditional_direction_value(records)

    # Her iki tabakada da LONG ve SHORT ayni p_up'a sahip (0,75 ve 0,25)
    # -> Council'in katkisi sifir, ama donus etkisi 0,50 gibi devasa.
    assert math.isclose(result["pooled_separation"], 0.0, abs_tol=1e-6)
    assert math.isclose(result["reversal_effect"], 0.50, abs_tol=1e-6)
    assert result["verdict"] == "no_incremental_information"


def test_thin_cells_are_marked_unusable_not_silently_dropped():
    """Bir tabakanın SHORT hücresi 25'in altındaysa separation
    hesaplanmaz -- ama tabaka raporda `usable: false` ile GÖRÜNÜR,
    sessizce yok sayılmaz (kullanıcı neden dışlandığını görebilmeli)."""
    records = []
    records += _rec("LONG", "UP", -0.005, 200) + _rec("LONG", "DOWN", -0.005, 200)
    records += _rec("SHORT", "UP", -0.005, 3) + _rec("SHORT", "DOWN", -0.005, 2)
    records += _rec("LONG", "UP", 0.005, 150) + _rec("LONG", "DOWN", 0.005, 150)
    records += _rec("SHORT", "UP", 0.005, 100) + _rec("SHORT", "DOWN", 0.005, 100)

    result = compute_conditional_direction_value(records)

    assert result["per_bucket"]["PRIOR_DOWN"]["usable"] is False
    assert result["per_bucket"]["PRIOR_DOWN"]["separation"] is None
    assert result["per_bucket"]["PRIOR_UP"]["usable"] is True
    # Ince tabaka pooled hesabina KATILMAMALI.
    assert math.isclose(result["pooled_separation"], 0.0, abs_tol=1e-6)


def test_fails_closed_below_minimum_sample():
    records = _rec("LONG", "UP", 0.005, 50)
    assert compute_conditional_direction_value(records) is None


def test_records_without_prior_return_are_excluded():
    """prior_return'ü olmayan kayıtlar tabakalanamaz -- fail-closed
    dışlanmalı, 'FLAT' varsayılmamalı (uydurma bağlam)."""
    records = _rec("LONG", "UP", None, 200) + _rec("SHORT", "DOWN", None, 200)
    assert compute_conditional_direction_value(records) is None
