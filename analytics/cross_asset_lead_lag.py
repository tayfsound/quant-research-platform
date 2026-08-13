"""Cross-Asset ve External Information — Faz 419-443 (Cognitive Core 2.0).

Watchlist'te zaten geleneksel risk varlıkları (^IXIC — Nasdaq, ^GSPC —
S&P 500) var, ama kripto sembollerinin bunlarla İLİŞKİSİ (risk-on/
risk-off rejim) hiçbir yerde gerçekten ölçülüp KULLANILMIYOR. Bu modül,
risk/cross_symbol_correlation.py'nin (aynı-anlı korelasyon) AKSİNE,
lead-lag (öncü-takipçi) ilişkisini ölçüyor: bir "lider" varlığın (ör.
^IXIC) getirileri, bir "takipçi" varlığın (ör. BTCUSDT) getirilerini KAÇ
BAR SONRA en güçlü şekilde açıklıyor — standart, literatürde tanımlı bir
cross-correlation function (CCF) analizi, icat edilmiş bir yöntem değil.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon/risk kararını burada
otomatik değiştirmiyor."""
import numpy as np

MIN_SAMPLE_SIZE = 30


def compute_lead_lag_correlation(
    leader_returns: list[float],
    follower_returns: list[float],
    max_lag: int = 5,
) -> dict | None:
    """leader_returns/follower_returns: AYNI uzunlukta, kronolojik sıralı
    GERÇEK dönemsel getiri serileri (hizalama çağıran tarafın sorumluluğu
    — risk/cross_symbol_correlation.py'nin kendi returns dict'iyle AYNI
    varsayım). lag=k: leader_returns[t] ile follower_returns[t+k]
    arasındaki korelasyon (k>0: lider öne geçmiş, takipçi geriden geliyor).

    <MIN_SAMPLE_SIZE gözlem varsa ya da seriler farklı uzunluktaysa
    fail-closed None döner."""
    if len(leader_returns) != len(follower_returns) or len(leader_returns) < MIN_SAMPLE_SIZE:
        return None

    leader = np.array(leader_returns, dtype=float)
    follower = np.array(follower_returns, dtype=float)
    n = len(leader)

    correlations: dict[int, float] = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a, b = leader[: n - lag] if lag > 0 else leader, follower[lag:]
        else:
            a, b = leader[-lag:], follower[: n + lag]
        if len(a) < MIN_SAMPLE_SIZE // 2 or a.std() == 0 or b.std() == 0:
            continue
        with np.errstate(invalid="ignore"):
            corr = float(np.corrcoef(a, b)[0, 1])
        if not np.isnan(corr):
            correlations[lag] = round(corr, 4)

    if not correlations:
        return None

    best_lag = max(correlations, key=lambda k: abs(correlations[k]))
    return {
        "correlations_by_lag": correlations,
        "best_lag": best_lag,
        "best_lag_correlation": correlations[best_lag],
        "sample_size": n,
    }
