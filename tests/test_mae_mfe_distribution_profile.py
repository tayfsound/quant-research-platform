"""Faz 479 — GPT'nin MAE/MFE revizyon tavsiyeleri (kullanıcı todo'su).

GPT'nin ana tezi: bu modül EDGE ölçmüyor, edge varsa onu hayatta tutacak
RİSK GEOMETRİSİNİ ölçüyor — ve tek bir P90 bunu anlatmaya yetmiyor.
"""
from analytics.mae_mfe_scientific import (
    compute_distribution_profile,
    evidence_tier,
)


def test_same_p90_completely_different_risk_geometry():
    """GPT'nin ASIL ARGÜMANI. İki dağılım AYNI P90'a sahip olabilir ama
    SL tasarımı açısından tamamen farklı dünyalardır. Tek nokta tahmini
    bunu gizler; profil gösterir."""
    # Iki dizi de AYNI p90'a (~3,3) sahip olacak sekilde kuruldu; fark
    # medyanda ve kuyrukta.
    # p90 bolgesi (indeks 85-94) ikisinde de AYNI (3,3); fark SADECE
    # medyanda (alt %85) ve kuyrukta (ust %5).
    dar = [2.4] * 85 + [3.3] * 10 + [3.9] * 5
    genis = [0.7] * 85 + [3.3] * 10 + [8.5] * 5

    p_dar = compute_distribution_profile(dar)
    p_genis = compute_distribution_profile(genis)

    # P90'lar neredeyse AYNI...
    assert abs(p_dar["quantiles"]["p90"] - p_genis["quantiles"]["p90"]) < 0.1
    # ...ama medyan ve P99 TAMAMEN farkli.
    assert p_dar["quantiles"]["median"] > 3 * p_genis["quantiles"]["median"]
    assert p_genis["quantiles"]["p99"] > 2 * p_dar["quantiles"]["p99"]


def test_evidence_tiers_follow_the_recommended_thresholds():
    """GPT: N>=10 arastirma icin tamam ama CANLI ac/kapa karari icin
    yeterli degil -- P90 zaten bir kuyruk metrigi, N=10'da birkac uc
    gozlemin insafinda."""
    assert evidence_tier(15) == "exploratory"
    assert evidence_tier(29) == "exploratory"
    assert evidence_tier(30) == "weak"
    assert evidence_tier(99) == "weak"
    assert evidence_tier(100) == "usable"
    assert evidence_tier(249) == "usable"
    assert evidence_tier(250) == "strong"
    assert evidence_tier(477) == "strong"


def test_narrow_ci_with_small_sample_is_flagged_as_a_trap():
    """GPT'nin somut örneği: SHORT/bear_trend/low/equity ->
    1,35% [1,34%, 1,38%] ama N=27. Bootstrap CI, gözlemler homojense
    yapay olarak dar çıkar; bu YÜKSEK GÜVEN demek DEĞİLDİR."""
    # Cok homojen, kucuk orneklem -> dar CI ama guvenilmez
    homojen_kucuk = [1.35, 1.36, 1.34, 1.35, 1.37, 1.35, 1.36, 1.34, 1.35, 1.36,
                     1.35, 1.35, 1.36, 1.34, 1.35, 1.36, 1.35, 1.34, 1.36, 1.35,
                     1.35, 1.36, 1.34, 1.35, 1.36, 1.35, 1.34]
    p = compute_distribution_profile(homojen_kucuk)

    assert p["sample_size"] == 27
    assert p["evidence_tier"] == "exploratory"
    assert p["narrow_ci_small_sample"] is True


def test_narrow_ci_with_large_sample_is_NOT_flagged():
    """Aynı darlık, BÜYÜK örneklemde meşrudur — uyarı sadece küçük N ile
    birleştiğinde anlamlı."""
    p = compute_distribution_profile([2.5 + (i % 5) * 0.01 for i in range(400)])
    assert p["evidence_tier"] == "strong"
    assert p["narrow_ci_small_sample"] is False


def test_wide_ci_small_sample_is_not_flagged_because_it_is_honest():
    """GPT'nin diğer örneği: LONG/transition/low -> 1,28% [0,12%, 5,75%],
    N=15. Bu kova ZATEN "bilmiyorum" diyor — tuzak DEĞİL, dürüst.
    Uyarı sadece SAHTE kesinlik için."""
    genis_kucuk = [0.1, 0.3, 0.6, 1.0, 1.3, 1.9, 2.6, 3.4, 4.2, 5.1, 5.8, 0.2, 0.9, 2.2, 3.9]
    p = compute_distribution_profile(genis_kucuk)

    assert p["evidence_tier"] == "exploratory"
    assert p["narrow_ci_small_sample"] is False


def test_profile_still_fails_closed_below_minimum():
    assert compute_distribution_profile([1.0] * 9) is None


def test_ci_is_reported_alongside_the_profile():
    p = compute_distribution_profile([1.0 + i * 0.1 for i in range(60)])
    assert p["ci"] is not None
    assert p["ci"]["ci_lower"] <= p["ci"]["point_estimate"] <= p["ci"]["ci_upper"]
    # CI, profildeki p90 ile AYNI quantile'i anlatmali.
    assert abs(p["ci"]["point_estimate"] - p["quantiles"]["p90"]) < 1e-9
