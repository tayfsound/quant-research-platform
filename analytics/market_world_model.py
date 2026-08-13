"""Market World Model — Faz 901-940 (Cognitive Core 5.0-6.0).

risk/predictive/monte_carlo.py GERÇEK geçmiş getirilerden bootstrap
örnekleme yapıyor ama TEKİL (iid) noktaları yeniden örnekliyor — bu,
getiriler arasındaki GERÇEK ardışık bağımlılığı (volatilite kümelenmesi,
momentum/mean-reversion otokorelasyonu) YOK EDİYOR, her nokta bağımsızmış
gibi karıştırıyor. Bu modül, standart, literatürde tanımlı bir teknik
olan Moving Block Bootstrap'i (Künsch, 1989) ekliyor — TEKİL noktalar
yerine ARDIŞIK BLOKLAR yeniden örnekleniyor, gerçek zaman-serisi
bağımlılık yapısı büyük ölçüde korunuyor. İcat edilmiş bir simülasyon
değil.

Kasıtlı olarak SADECE simülasyon/rapor — hiçbir pozisyon/risk kararını
burada otomatik değiştirmiyor."""
import numpy as np

DEFAULT_N_PATHS = 1000


def compute_block_bootstrap_paths(
    returns: list[float],
    block_size: int,
    path_length: int,
    n_paths: int = DEFAULT_N_PATHS,
    random_seed: int = 42,
) -> dict | None:
    """returns: GERÇEK kronolojik getiri serisi. block_size: yeniden
    örneklenen ardışık blok uzunluğu (>=1). path_length: üretilecek her
    yolun kaç dönem olacağı. <block_size*2 gözlemle ya da geçersiz
    parametrelerle fail-closed None döner — icat edilmiş bir simülasyon
    sonucu asla üretilmez. random_seed: tekrarlanabilirlik için sabit."""
    if block_size < 1 or path_length < 1 or len(returns) < block_size * 2:
        return None

    arr = np.array(returns, dtype=float)
    n = len(arr)
    n_blocks_available = n - block_size + 1
    if n_blocks_available < 1:
        return None

    rng = np.random.default_rng(random_seed)
    n_blocks_needed = int(np.ceil(path_length / block_size))

    cumulative_returns = np.empty(n_paths)
    for i in range(n_paths):
        path: list[float] = []
        for _ in range(n_blocks_needed):
            start = int(rng.integers(0, n_blocks_available))
            path.extend(arr[start:start + block_size])
        path = path[:path_length]
        compounded = 1.0
        for r in path:
            compounded *= (1.0 + r)
        cumulative_returns[i] = compounded - 1.0

    return {
        "mean_cumulative_return": round(float(cumulative_returns.mean()), 6),
        "p5_cumulative_return": round(float(np.quantile(cumulative_returns, 0.05)), 6),
        "p95_cumulative_return": round(float(np.quantile(cumulative_returns, 0.95)), 6),
        "worst_cumulative_return": round(float(cumulative_returns.min()), 6),
        "n_paths": n_paths,
        "block_size": block_size,
        "path_length": path_length,
    }
