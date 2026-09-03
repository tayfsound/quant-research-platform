"""Faz 407 — kullanıcı isteği: ölçtüğümüz her verinin zaman içindeki
stabilitesini de ölçelim ("dördüncü boyut"). compute_stability() saf
matematiğini test ediyor — gerçek modüllere bağlanması ayrı testlerde
(ör. tests/test_cross_symbol_correlation.py, tests/test_historical_
analog_engine.py)."""
from analytics.measurement_stability import compute_stability


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
