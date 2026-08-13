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
