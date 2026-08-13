"""Causal Cognitive Core — Faz 861-900 (Cognitive Core 4.0).

Sistemdeki TÜM ilişki sinyalleri (feature importance, risk/cross_symbol_
correlation.py, analytics/correlation_breakdown.py, analytics/cross_
asset_lead_lag.py) KORELASYON tabanlı — "X ile Y birlikte hareket ediyor"
ile "X, Y'yi öngörüyor" arasındaki farkı ayırt etmiyorlar. cross_asset_
lead_lag.py en yüksek korelasyonlu gecikmeyi buluyor ama bu YİNE korelasyon,
nedensellik değil.

Bu modül standart, literatürde kesin tanımlı bir nedensellik testi
ekliyor: Granger Causality (Granger, 1969) — statsmodels.tsa.stattools
(pairs_trading.py'nin zaten kullandığı AYNI kütüphane, farklı bir test).
X'in geçmiş değerleri, Y'nin gelecekteki değerlerini, Y'nin SADECE kendi
geçmişinin açıklayabileceğinden İSTATİSTİKSEL OLARAK ANLAMLI ÖLÇÜDE FAZLA
açıklıyor mu — "öngörücü nedensellik," felsefi/metafizik bir nedensellik
iddiası değil.

Kasıtlı olarak SADECE tespit/rapor — hiçbir pozisyon/risk kararını
otomatik değiştirmiyor."""

MIN_SAMPLE_SIZE = 30
SIGNIFICANCE_LEVEL = 0.05


def compute_granger_causality(
    cause_series: list[float],
    effect_series: list[float],
    max_lag: int = 5,
) -> dict | None:
    """cause_series/effect_series: AYNI uzunlukta, kronolojik sıralı
    GERÇEK dönemsel getiri (ya da başka bir zaman serisi) gözlemleri.
    "cause_series, effect_series'i Granger-nedensel olarak öngörüyor mu"
    sorusuna, her lag için F-testi p-value'su hesaplayıp en düşük
    (en güçlü kanıt) olanı raporlayarak cevap verir. <MIN_SAMPLE_SIZE
    gözlem, uzunluk uyuşmazlığı ya da statsmodels'in testi çalıştıramadığı
    dejenere serilerde (ör. sabit değerler) fail-closed None döner —
    icat edilmiş bir p-value asla üretilmez."""
    if len(cause_series) != len(effect_series) or len(cause_series) < MIN_SAMPLE_SIZE:
        return None

    import numpy as np
    from statsmodels.tsa.stattools import grangercausalitytests

    data = np.column_stack([effect_series, cause_series])  # statsmodels: [etki, sebep] sırası

    try:
        results = grangercausalitytests(data, maxlag=max_lag)
    except Exception:
        return None

    p_values_by_lag = {}
    for lag, (test_results, _) in results.items():
        p_value = test_results.get("ssr_ftest", (None, None))[1]
        if p_value is not None:
            p_values_by_lag[lag] = round(float(p_value), 6)

    if not p_values_by_lag:
        return None

    best_lag = min(p_values_by_lag, key=lambda lag: p_values_by_lag[lag])
    best_p_value = p_values_by_lag[best_lag]

    return {
        "p_values_by_lag": p_values_by_lag,
        "best_lag": best_lag,
        "best_p_value": best_p_value,
        "granger_causes": bool(best_p_value < SIGNIFICANCE_LEVEL),
        "sample_size": len(cause_series),
    }
