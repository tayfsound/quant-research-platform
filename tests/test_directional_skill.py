"""Faz 458 — analytics/directional_skill.py birim testleri.

Proje disiplini (bkz. plan dosyası "Doğrulama (genel)"): her yeni saf
fonksiyon, DAHA ÖNCE ELLE HESAPLANMIŞ gerçek bir sonucu yeniden
üretebilmeli. Buradaki ana test tam olarak bunu yapıyor — 2026-09-08
akşamı canlı `decisions` tablosunda ölçülen 9 güven kovasını yeniden
kurup, elle hesaplanan Murphy ayrıştırmasının aynısının çıktığını
doğruluyor.
"""
import math

from analytics.directional_skill import (
    compute_benchmark_relative_skill,
    compute_daily_sign_test,
    compute_murphy_decomposition,
    compute_pesaran_timmermann,
)

# 2026-09-08 akşamı GERÇEK canlı veriden (quantdb, son 21 gün, 1sa ufuk,
# %0,05 nötr bant, cascade A/B verisi hariç) ölçülen güven kovaları:
# (gözlem sayısı, kovanın ortalama confidence'ı, kovanın gerçek isabeti)
GERCEK_KOVALAR = [
    (44, 0.0130, 0.4545), (79, 0.1468, 0.4430), (86, 0.2725, 0.4767),
    (746, 0.3653, 0.4276), (2802, 0.4582, 0.4161), (1653, 0.5285, 0.4235),
    (1014, 0.6506, 0.4379), (1172, 0.7483, 0.4121), (124, 0.8221, 0.4194),
]


def _predictions_from_buckets(buckets) -> list[tuple[float, bool]]:
    """Kova özetini, aynı ayrıştırmayı üreten ham tahmin listesine çevirir.
    Kova içindeki her gözlem AYNI confidence'a sahip olduğu için kovanın
    ortalama tahmini birebir korunur -- Murphy ayrıştırması zaten kova
    ortalamasıyla çalıştığından bu sadık bir yeniden kurulum."""
    predictions: list[tuple[float, bool]] = []
    for n, confidence, hit_rate in buckets:
        hits = round(n * hit_rate)
        predictions.extend([(confidence, True)] * hits)
        predictions.extend([(confidence, False)] * (n - hits))
    return predictions


def test_murphy_decomposition_reproduces_the_real_2026_09_08_measurement():
    """Elle hesaplanan gerçek sonuç: Uncertainty 0,2440 / Reliability
    0,0316 / Resolution 0,000108 / Brier 0,2754 / BSS −0,1289.

    Bu testin ASIL iddiası tek tek sayılar değil, o gece varılan
    METODOLOJİK sonuç: reliability, resolution'ın ~292 katı -- yani
    "rastgeleden kötü" manşetinin büyük kısmı kalibrasyon kusuru, gerçek
    bilgi (resolution) neredeyse sıfır."""
    result = compute_murphy_decomposition(_predictions_from_buckets(GERCEK_KOVALAR))

    assert result is not None
    assert result["sample_size"] == 7720
    assert result["bins_used"] == 9
    assert math.isclose(result["uncertainty"], 0.2440, abs_tol=0.0005)
    assert math.isclose(result["reliability"], 0.0316, abs_tol=0.0005)
    assert math.isclose(result["resolution"], 0.000108, abs_tol=0.00002)
    assert math.isclose(result["brier_score"], 0.2754, abs_tol=0.0005)
    assert math.isclose(result["brier_skill_score"], -0.1289, abs_tol=0.002)

    # Asil metodolojik bulgu.
    assert result["resolution_exceeds_reliability"] is False
    assert result["reliability"] / result["resolution"] > 200

    # "Kalibrasyonu duzeltirsek ne kazaniriz" -- 0,2754'ten 0,2439'a, ama
    # bu SIFIR bilgi eklemeden gelen kozmetik bir kazanc.
    assert math.isclose(result["calibrated_brier_floor"], 0.2439, abs_tol=0.0005)


def test_reported_brier_is_the_true_brier_not_derived_from_components():
    """Bu test bir TASARIM KUSURU yakaladı (ilk sürümde Brier bileşenlerden
    türetiliyordu): kova İÇİ olasılık varyansı varsa klasik üç terimli
    ayrıştırma gerçek Brier'i tam kurmaz. Rastgele, [0,1] boyunca yayılmış
    olasılıklarda fark ~0,001 çıkıyor.

    Doğru davranış: raporlanan `brier_score` HER ZAMAN gerçek tanımdan
    gelmeli, kalan fark ise gizlenmeyip `decomposition_residual` olarak
    açıkça görünmeli."""
    import random

    rng = random.Random(11)
    predictions = [(rng.random(), rng.random() < 0.45) for _ in range(2000)]
    result = compute_murphy_decomposition(predictions)

    direct = sum((p - (1.0 if o else 0.0)) ** 2 for p, o in predictions) / len(predictions)
    assert math.isclose(direct, result["brier_score"], abs_tol=1e-6)

    rebuilt = result["reliability"] - result["resolution"] + result["uncertainty"]
    assert math.isclose(
        rebuilt + result["decomposition_residual"], result["brier_score"], abs_tol=1e-5,
    )
    # Kova ici varyans GERCEKTEN sifirdan farkli -- yani artik yaninin
    # varligi olculuyor, sessizce yutulmuyor.
    assert result["decomposition_residual"] > 0.0005


def test_decomposition_residual_is_zero_when_probabilities_are_constant_per_bin():
    """Gerçek ölçümümüzde (kova başına tek bir confidence) kalan TAM
    sıfır olmalı -- yani 2026-09-08 ayrıştırması yanlılıktan etkilenmiyor,
    yukarıdaki ~0,001'lik fark sadece yapay rastgele veriye özgü."""
    result = compute_murphy_decomposition(_predictions_from_buckets(GERCEK_KOVALAR))
    assert math.isclose(result["decomposition_residual"], 0.0, abs_tol=1e-6)


def test_perfect_forecaster_has_high_resolution_and_zero_reliability():
    """Kalibre ve bilgili bir tahminci: reliability ~0, resolution
    yüksek, BSS pozitif. Fonksiyonun sadece bizim kötü verimizde değil,
    İYİ veride de doğru davrandığının kontrolü."""
    predictions = [(1.0, True)] * 500 + [(0.0, False)] * 500
    result = compute_murphy_decomposition(predictions)

    assert math.isclose(result["reliability"], 0.0, abs_tol=1e-9)
    assert math.isclose(result["resolution"], result["uncertainty"], abs_tol=1e-9)
    assert math.isclose(result["brier_score"], 0.0, abs_tol=1e-9)
    assert math.isclose(result["brier_skill_score"], 1.0, abs_tol=1e-9)
    assert result["resolution_exceeds_reliability"] is True


def test_constant_forecast_has_exactly_zero_resolution():
    """Hep aynı olasılığı söyleyen tahminci: resolution TAM sıfır --
    literatürdeki "climatological forecast" tanımı. Bizim sistemimizin
    yaklaştığı uç bu."""
    predictions = [(0.6, i % 100 < 42) for i in range(1000)]
    result = compute_murphy_decomposition(predictions)

    assert math.isclose(result["resolution"], 0.0, abs_tol=1e-9)
    assert result["resolution_exceeds_reliability"] is False


def test_murphy_fails_closed_below_minimum_sample():
    assert compute_murphy_decomposition([(0.5, True)] * 29) is None


def _records(long_up, long_down, short_up, short_down, day="2026-09-01"):
    out = []
    out += [{"direction": "LONG", "forward_label": "UP", "day": day}] * long_up
    out += [{"direction": "LONG", "forward_label": "DOWN", "day": day}] * long_down
    out += [{"direction": "SHORT", "forward_label": "UP", "day": day}] * short_up
    out += [{"direction": "SHORT", "forward_label": "DOWN", "day": day}] * short_down
    return out


def test_benchmark_relative_skill_reproduces_the_real_negative_edge():
    """Gerçek veri (2026-09-08): piyasa %51,94 yükselmiş; LONG isabeti
    %45,50 (n=5818), SHORT isabeti %36,20 (n=3109). Yani LONG −6,4pp,
    SHORT −11,9pp beceriyle KENDİ benchmark'ının altında.

    Kayıtlar o gerçek dağılımdan yeniden kuruluyor."""
    long_up = round(5818 * 0.4550)
    short_down = round(3109 * 0.3620)
    records = _records(
        long_up=long_up, long_down=5818 - long_up,
        short_up=3109 - short_down, short_down=short_down,
    )
    result = compute_benchmark_relative_skill(records)

    assert result is not None
    assert math.isclose(result["unconditional_up_rate"], 0.5194, abs_tol=0.002)

    long_stats = result["per_direction"]["LONG"]
    assert math.isclose(long_stats["hit_rate"], 0.4550, abs_tol=0.001)
    assert math.isclose(long_stats["skill"], -0.064, abs_tol=0.003)

    short_stats = result["per_direction"]["SHORT"]
    assert math.isclose(short_stats["hit_rate"], 0.3620, abs_tol=0.001)
    assert math.isclose(short_stats["skill"], -0.119, abs_tol=0.003)

    # Asil bulgu: HER IKI yon de kendi benchmark'inin ALTINDA.
    assert long_stats["skill"] < 0
    assert short_stats["skill"] < 0


def test_benchmark_is_not_naive_fifty_percent():
    """Metodolojik düzeltmenin kendisi: yükselen bir örneklemde %55
    isabetli bir "hep LONG" tahminci %50'ye göre iyi görünür ama gerçek
    benchmark'ına (aynı %55) göre TAM SIFIR beceri gösterir."""
    records = _records(long_up=550, long_down=450, short_up=0, short_down=0)
    result = compute_benchmark_relative_skill(records)

    assert math.isclose(result["per_direction"]["LONG"]["hit_rate"], 0.55, abs_tol=1e-6)
    assert math.isclose(result["per_direction"]["LONG"]["skill"], 0.0, abs_tol=1e-6)


def test_pesaran_timmermann_detects_real_skill_and_its_sign():
    """Gerçek öngörü gücü olan bir tahminci pozitif, istatistiksel olarak
    anlamlı bir S üretmeli."""
    records = _records(long_up=700, long_down=300, short_up=300, short_down=700)
    result = compute_pesaran_timmermann(records)

    assert result is not None
    assert result["direction_of_skill"] == "positive"
    assert result["statistic"] > 0
    assert result["significant_at_5pct"] is True
    assert math.isclose(result["hit_rate"], 0.70, abs_tol=1e-6)


def test_pesaran_timmermann_flags_systematically_inverted_signal():
    """Bizim durumumuz: sistematik TERS yön. Tek taraflı standart kullanım
    bunu "anlamsız" diye geçerdi; çift taraflı p-değeri ANLAMLI NEGATİF
    olarak yakalamalı."""
    records = _records(long_up=300, long_down=700, short_up=700, short_down=300)
    result = compute_pesaran_timmermann(records)

    assert result["direction_of_skill"] == "negative"
    assert result["statistic"] < 0
    assert result["significant_at_5pct"] is True


def test_pesaran_timmermann_fails_closed_when_all_predictions_are_one_sided():
    """Tüm tahminler LONG ise varyans paydası çöker -- uydurma bir
    istatistik yerine None."""
    records = _records(long_up=500, long_down=500, short_up=0, short_down=0)
    assert compute_pesaran_timmermann(records) is None


def test_pesaran_timmermann_always_reports_the_independence_caveat():
    """123 sembolün aynı piyasa hareketini paylaşması bu testin
    varsayımını ihlal ediyor; rapor bunu SESSİZCE geçmemeli."""
    records = _records(long_up=700, long_down=300, short_up=300, short_down=700)
    assert compute_pesaran_timmermann(records)["independence_assumption_violated"] is True


def test_daily_sign_test_reproduces_the_six_negative_days():
    """Gerçek veri: 1-6 Eylül'ün ALTISINDA da beceri negatifti. Günleri
    bağımsız sayan işaret testi p≈0,031 (iki taraflı, 6/6) vermeli --
    örtüşen örneklem itirazını aşan asıl kanıt bu."""
    records = []
    # Her gunde LONG agirlikli, hem LONG hem SHORT tarafi benchmark'in
    # altinda kalacak sekilde -- gercek gunluk tablodaki desen.
    for day in ("2026-09-01", "2026-09-02", "2026-09-03",
                "2026-09-04", "2026-09-05", "2026-09-06"):
        records += _records(long_up=40, long_down=60, short_up=60, short_down=40, day=day)

    result = compute_daily_sign_test(records)

    assert result is not None
    assert result["days_evaluated"] == 6
    assert result["negative_skill_days"] == 6
    assert result["positive_skill_days"] == 0
    assert result["consistent_direction"] == "negative"
    assert math.isclose(result["p_value"], 0.03125, abs_tol=1e-6)
    assert result["significant_at_5pct"] is True


def test_daily_sign_test_discards_thin_days():
    """Gerçek veride 21 günün 15'i 1-50 karar arasıydı; bunlar "gün"
    sayılırsa test gürültüyle dolar."""
    records = _records(long_up=40, long_down=60, short_up=60, short_down=40, day="2026-09-01")
    records += _records(long_up=1, long_down=1, short_up=1, short_down=1, day="2026-09-02")
    records += _records(long_up=40, long_down=60, short_up=60, short_down=40, day="2026-09-03")
    records += _records(long_up=40, long_down=60, short_up=60, short_down=40, day="2026-09-04")

    result = compute_daily_sign_test(records)

    assert result["days_evaluated"] == 3  # ince gun elendi
    assert all(d["day"] != "2026-09-02" for d in result["per_day"])


def test_daily_sign_test_needs_at_least_three_days():
    records = _records(long_up=40, long_down=60, short_up=60, short_down=40, day="2026-09-01")
    records += _records(long_up=40, long_down=60, short_up=60, short_down=40, day="2026-09-02")
    assert compute_daily_sign_test(records) is None


def test_daily_sign_test_uses_each_days_own_benchmark():
    """Piyasa rejimi günden güne değiştiği için sabit bir benchmark
    yanıltıcı olurdu: güçlü yükselen bir günde %55 LONG isabeti BAŞARI
    değil, o günün kendi %55'ine eşit performanstır."""
    records = []
    for day in ("2026-09-01", "2026-09-02", "2026-09-03"):
        # Piyasa o gun %55 yukselmis, biz de hep LONG deyip %55 tutturmusuz.
        records += _records(long_up=55, long_down=45, short_up=0, short_down=0, day=day)

    result = compute_daily_sign_test(records)

    assert result["negative_skill_days"] == 0
    assert result["positive_skill_days"] == 0
    for d in result["per_day"]:
        assert math.isclose(d["skill"], 0.0, abs_tol=1e-6)
