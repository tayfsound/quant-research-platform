"""Faz 407 — kullanıcı isteği: ölçtüğümüz her verinin zaman içindeki
stabilitesini de ölçelim ("dördüncü boyut"). compute_stability() saf
matematiğini test ediyor — gerçek modüllere bağlanması ayrı testlerde
(ör. tests/test_cross_symbol_correlation.py, tests/test_historical_
analog_engine.py)."""
from datetime import UTC, datetime, timedelta

from analytics.measurement_stability import compute_stability, select_non_overlapping_snapshots


def test_returns_none_for_fewer_than_two_values():
    """Fail-closed: tek bir ölçüm için 'stabil'/'oynak' demek anlamsız —
    icat edilmiş bir skor asla üretilmemeli."""
    assert compute_stability([]) is None
    assert compute_stability([0.7]) is None
    assert compute_stability([None, 0.7]) is None


def test_computes_real_mean_and_std():
    result = compute_stability([0.8, 0.9, 0.7])
    assert abs(result["mean"] - 0.8) < 1e-9
    assert result["n"] == 3
    assert result["min"] == 0.7
    assert result["max"] == 0.9
    # population std of [0.8,0.9,0.7]
    assert abs(result["std"] - 0.08164965809) < 1e-6


def test_ignores_none_values_in_the_series():
    """Bazı geçmiş snapshot'larda ilgili anahtar hiç oy kullanmamış/hiç
    eşleşmemiş olabilir (None) — bunlar seriden ÇIKARILIR, icat edilmiş
    bir 0 asla eklenmez."""
    with_none = compute_stability([0.8, None, 0.9, None, 0.7])
    without_none = compute_stability([0.8, 0.9, 0.7])
    assert with_none == without_none


def test_high_std_case_matches_real_nvda_amd_finding():
    """Gerçek bulgu (2026-09-03): NVDA-AMD'nin kayan-pencere korelasyonu
    std=0.181 (BTC-ETH'nin ~4.3 katı) — bu regresyon testi o büyüklük
    farkının compute_stability ile de doğru yakalandığını doğruluyor."""
    btc_eth = compute_stability([0.853] * 10)  # fiilen sabit -> std=0
    nvda_amd_like = compute_stability([0.09, 0.86, 0.52, 0.15, 0.78, 0.31, 0.60, 0.20, 0.75, 0.40])
    assert btc_eth["std"] < nvda_amd_like["std"]


def test_coefficient_of_variation_is_unitless_and_comparable():
    """CV, farklı ölçeklerdeki iki metriği (ör. korelasyon [-1,1] vs
    win_rate [0,1]) karşılaştırılabilir kılıyor. Aynı orantısal
    değişkenliğe sahip iki seri (biri 10x büyük ölçekte) AYNI CV'yi
    üretmeli."""
    small_scale = compute_stability([0.08, 0.10, 0.09, 0.11])
    large_scale = compute_stability([0.8, 1.0, 0.9, 1.1])
    assert abs(small_scale["coefficient_of_variation"] - large_scale["coefficient_of_variation"]) < 1e-9


def test_zero_mean_gives_undefined_coefficient_of_variation():
    """mean==0 iken std/|mean| tanımsız — icat edilmiş bir bölme sonucu
    (ör. sonsuz ya da 0) asla üretilmemeli, fail-closed None."""
    result = compute_stability([-0.5, 0.5])
    assert result["mean"] == 0.0
    assert result["coefficient_of_variation"] is None


def test_sign_consistency_pct_is_1_when_all_values_share_the_mean_sign():
    result = compute_stability([0.8, 0.9, 0.7])
    assert result["sign_consistency_pct"] == 1.0


def test_sign_consistency_pct_catches_a_flipping_series_low_cv_can_miss():
    """Faz 429 — CV'nin YAKALAYAMADIĞI durum: işaret sürekli değişiyor
    (+0.3/-0.2/+0.4/-0.3/+0.2) ama std/|mean| oranı (CV) küçük bir
    ortalamaya göre yüksek çıkmayabilir. sign_consistency_pct bunu
    doğrudan ölçüyor."""
    flipping = compute_stability([0.3, -0.2, 0.4, -0.3, 0.2])
    assert flipping["mean"] > 0
    # 5 değerden 3'ü pozitif (mean'in işareti) -> %60.
    assert flipping["sign_consistency_pct"] == 0.6


def test_sign_consistency_pct_is_none_when_mean_is_zero():
    """CV ile AYNI ilke: mean==0 iken 'hangi işaret doğru' tanımsız —
    icat edilmiş bir sonuç asla üretilmez."""
    result = compute_stability([-0.5, 0.5])
    assert result["sign_consistency_pct"] is None


def _snap(minutes_ago: int) -> dict:
    ts = datetime(2026, 9, 7, 12, 0, tzinfo=UTC) - timedelta(minutes=minutes_ago)
    return {"created_at": ts.isoformat()}


def test_select_non_overlapping_snapshots_thins_a_densely_sampled_series():
    """Faz 431 — kullanıcı isteği: "düzeltelim." Gerçek bulgu:
    correlation_snapshots ~18dk kadansla kaydediliyor ama 250 mumluk
    (~2,6 gün) kayan pencereden hesaplanıyor — ardışık snapshot'lar
    ~%99 aynı ham veriyi paylaşıyor. min_spacing_minutes pencere
    uzunluğu kadar (ör. 3750dk) verilince, sadece GERÇEKTEN o kadar
    aralıklı olan snapshot'lar seçilmeli."""
    dense = [_snap(m) for m in range(0, 300, 18)]  # ~18dk aralıklı, 0-282dk
    selected = select_non_overlapping_snapshots(dense, min_spacing_minutes=100)
    # 100dk aralıkla en fazla ~3 tane (0, ~108, ~216) seçilebilir -- kesin
    # sayı yerine üst sınırı ve gerçekten aralıklı olduğunu doğruluyoruz.
    assert len(selected) < len(dense)
    kept_minutes = sorted(
        (datetime(2026, 9, 7, 12, 0, tzinfo=UTC) - datetime.fromisoformat(s["created_at"])).total_seconds() / 60
        for s in selected
    )
    for a, b in zip(kept_minutes, kept_minutes[1:]):
        assert (b - a) >= 100 - 1e-6


def test_select_non_overlapping_snapshots_keeps_everything_when_spacing_is_already_sufficient():
    sparse = [_snap(0), _snap(200), _snap(400)]
    selected = select_non_overlapping_snapshots(sparse, min_spacing_minutes=100)
    assert len(selected) == 3


def test_select_non_overlapping_snapshots_returns_few_points_when_history_is_too_short():
    """Faz 431'in gerçek canlı durumu: sadece ~4 günlük ham geçmiş var,
    2,6 günlük pencereyle 12 bağımsız nokta için ~31 gün gerekir — icat
    edilmiş fazladan nokta üretilmez, gerçek veri kadarı döner."""
    only_four_days = [_snap(m) for m in range(0, 4 * 24 * 60, 18)]
    selected = select_non_overlapping_snapshots(only_four_days, min_spacing_minutes=3750)
    assert 1 <= len(selected) <= 2


def test_select_non_overlapping_snapshots_is_a_noop_for_non_positive_spacing():
    dense = [_snap(m) for m in range(0, 50, 5)]
    assert select_non_overlapping_snapshots(dense, min_spacing_minutes=0) == dense


def test_select_non_overlapping_snapshots_respects_limit():
    sparse = [_snap(0), _snap(200), _snap(400), _snap(600)]
    selected = select_non_overlapping_snapshots(sparse, min_spacing_minutes=100, limit=2)
    assert len(selected) == 2
