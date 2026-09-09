"""MAE/MFE Bilimsel Motoru — Faz 469-493 (Cognitive Core 2.0).

analytics/mae_mfe.py::compute_conditional_mae_distribution() ve
compute_optimal_barrier() nokta tahminleri (ör. p90 MAE = 0.023) üretiyor
ama bu tahminlerin GERÇEK belirsizliğini hiç raporlamıyordu — küçük bir
örneklemden (ör. 25 trade) çıkan bir yüzdelik, büyük bir örneklemden
(ör. 500 trade) çıkanla AYNI kesinlikte sunuluyordu. Bu modül, standart,
literatürde tanımlı bir teknik olan bootstrap resampling ile GERÇEK bir
güven aralığı ekliyor — icat edilmiş bir belirsizlik formülü değil.

Kasıtlı olarak SADECE mevcut nokta tahminlerinin ÜZERİNE bir belirsizlik
katmanı — compute_conditional_mae_distribution/compute_optimal_barrier'ı
DEĞİŞTİRMİYOR, üzerlerine ayrıca çağrılabilir bağımsız bir araç."""
import numpy as np

DEFAULT_N_BOOTSTRAP = 1000
DEFAULT_CI_LEVEL = 0.95
MIN_SAMPLE_SIZE = 10


def bootstrap_quantile_ci(
    values: list[float],
    quantile: float,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    ci_level: float = DEFAULT_CI_LEVEL,
    random_seed: int = 42,
) -> dict | None:
    """values: GERÇEK gözlem listesi (ör. bir koşul kovasındaki |MAE|
    değerleri). n<MIN_SAMPLE_SIZE ile fail-closed None döner — icat
    edilmiş bir güven aralığı asla üretilmez. random_seed: tekrarlanabilirlik
    için sabit varsayılan — aynı girdiyle her çağrı AYNI sonucu üretir."""
    if len(values) < MIN_SAMPLE_SIZE:
        return None

    arr = np.array(values, dtype=float)
    rng = np.random.default_rng(random_seed)
    point_estimate = float(np.quantile(arr, quantile))

    bootstrap_estimates = np.array([
        np.quantile(rng.choice(arr, size=len(arr), replace=True), quantile)
        for _ in range(n_bootstrap)
    ])

    alpha = 1 - ci_level
    lower = float(np.quantile(bootstrap_estimates, alpha / 2))
    upper = float(np.quantile(bootstrap_estimates, 1 - alpha / 2))

    return {
        "point_estimate": round(point_estimate, 6),
        "ci_lower": round(lower, 6),
        "ci_upper": round(upper, 6),
        "ci_level": ci_level,
        "sample_size": len(values),
    }


# --- Faz 479: GPT'nin MAE/MFE revizyon tavsiyeleri (kullanici todo'su) ---

# GPT'nin onerdigi kanit kademeleri. "Sabit yasa degil, senin verinde
# geriye donuk dogrulamayla belirlenmeli" -- oyle isaretlendi.
EVIDENCE_TIERS = ((250, "strong"), (100, "usable"), (30, "weak"), (0, "exploratory"))
# "Dar CI + kucuk N = yuksek guven DEGIL" uyarisi icin esikler. Bootstrap
# CI, gozlemler homojense yapay olarak dar cikabilir.
SUSPICIOUS_CI_MAX_SAMPLE = 100
SUSPICIOUS_CI_RELATIVE_WIDTH = 0.10


def evidence_tier(sample_size: int) -> str:
    """N'e gore kanit seviyesi. GPT'nin uyarisi: mevcut MIN_SAMPLE_SIZE=10
    ARASTIRMA icin tamam ama CANLI ac/kapa karari icin cok dusuk -- P90
    zaten bir KUYRUK metrigi, N=10'da birkac uc gozlemin insafinda."""
    for threshold, tier in EVIDENCE_TIERS:
        if sample_size >= threshold:
            return tier
    return "exploratory"


def compute_distribution_profile(
    values: list[float],
    quantile: float = 0.9,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    ci_level: float = DEFAULT_CI_LEVEL,
    random_seed: int = 42,
) -> dict | None:
    """Faz 479 — kullanici todo'sundaki GPT tavsiyelerinin modul tarafi.

    GPT'nin ana tezi: bu modul EDGE olcmuyor, edge varsa onu hayatta
    tutacak RISK GEOMETRISINI olcuyor. Ve tek bir P90 yetmiyor:

        median 0,8% + P90 3,3% + P99 8,5%
    ile
        median 2,5% + P90 3,3% + P99 4,0%
    ayni P90'a sahip ama SL tasarimi acisindan TAMAMEN farkli iki dunya.

    Doner:
      quantiles  — median/p75/p90/p95/p99/max (tek nokta degil PROFIL)
      ci         — secilen quantile'in bootstrap guven araligi
      evidence_tier — exploratory/weak/usable/strong (bkz. evidence_tier)
      narrow_ci_small_sample — "dar CI + kucuk N" TUZAK uyarisi. GPT'nin
        ornegi: 1,35% [1,34%, 1,38%] ama N=27. Bootstrap CI, gozlemler
        homojense dar cikar; bu GUVEN demek degildir.

    n<MIN_SAMPLE_SIZE ile fail-closed None (mevcut davranisla ayni)."""
    if len(values) < MIN_SAMPLE_SIZE:
        return None

    arr = np.array(values, dtype=float)
    ci = bootstrap_quantile_ci(
        values, quantile=quantile, n_bootstrap=n_bootstrap,
        ci_level=ci_level, random_seed=random_seed,
    )

    narrow_ci = None
    if ci is not None and ci["point_estimate"] != 0:
        relative_width = (ci["ci_upper"] - ci["ci_lower"]) / abs(ci["point_estimate"])
        narrow_ci = bool(
            len(values) < SUSPICIOUS_CI_MAX_SAMPLE
            and relative_width < SUSPICIOUS_CI_RELATIVE_WIDTH
        )

    return {
        "quantiles": {
            "median": round(float(np.quantile(arr, 0.50)), 6),
            "p75": round(float(np.quantile(arr, 0.75)), 6),
            "p90": round(float(np.quantile(arr, 0.90)), 6),
            "p95": round(float(np.quantile(arr, 0.95)), 6),
            "p99": round(float(np.quantile(arr, 0.99)), 6),
            "max": round(float(arr.max()), 6),
        },
        "ci": ci,
        "sample_size": len(values),
        "evidence_tier": evidence_tier(len(values)),
        "narrow_ci_small_sample": narrow_ci,
    }

