"""Correlation Breakdown Detection.

Neden gerekli: risk/cross_symbol_correlation.py ve risk/limits/portfolio.py
(VaR/kovaryans) TEK bir ANLIK korelasyon matrisine güveniyor — ama
korelasyon zamanla kırılabilir (ör. gerçek bir rejim değişikliğinde,
genelde birlikte hareket eden iki varlık ayrışabilir; bu oturumda gerçek
bir örneği yaşandı — altın/gümüş kill switch olayı). Eğer risk modeli
ESKİ (baseline) bir korelasyon varsayımıyla çalışıyorsa, gerçek portföy
riski VaR'ın hesapladığından daha yüksek olabilir.

Kasıtlı olarak SADECE tespit/rapor — hiçbir risk limitini veya pozisyon
büyüklüğünü burada otomatik DEĞİŞTİRMİYOR."""
import numpy as np

MIN_WINDOW_SIZE = 20
BREAKDOWN_THRESHOLD = 0.3  # korelasyondaki mutlak değişim


def compute_correlation_breakdown(
    returns: dict[str, list[float]],
    baseline_window: int,
    recent_window: int,
    min_window_size: int = MIN_WINDOW_SIZE,
    breakdown_threshold: float = BREAKDOWN_THRESHOLD,
) -> dict:
    """returns: {symbol: [kronolojik sırayla GERÇEK dönemsel getiri, ...]}.
    baseline_window: serinin BAŞINDAN itibaren "eski/referans" korelasyon
    için kaç gözlem kullanılacağı. recent_window: serinin SONUNDAN
    itibaren "güncel" korelasyon için kaç gözlem kullanılacağı (iki
    pencerenin kesişmemesi çağıran tarafın sorumluluğu — burada sadece
    dilim alınır).

    min_window_size altında yeterli veri olan sembol/çift fail-closed
    dışlanır (NaN korelasyon üreten sabit-getiri serileri dahil).
    |baseline_corr - recent_corr| > breakdown_threshold olan çiftler
    breakdown_detected=True ile işaretlenir."""
    symbols = [s for s, r in returns.items() if len(r) >= baseline_window + recent_window]
    if len(symbols) < 2:
        return {}

    results: dict[str, dict] = {}
    for i, sym_a in enumerate(symbols):
        for sym_b in symbols[i + 1:]:
            baseline_a = returns[sym_a][:baseline_window]
            baseline_b = returns[sym_b][:baseline_window]
            recent_a = returns[sym_a][-recent_window:]
            recent_b = returns[sym_b][-recent_window:]

            if len(baseline_a) < min_window_size or len(recent_a) < min_window_size:
                continue

            with np.errstate(invalid="ignore"):
                baseline_corr = float(np.corrcoef(baseline_a, baseline_b)[0, 1])
                recent_corr = float(np.corrcoef(recent_a, recent_b)[0, 1])

            if np.isnan(baseline_corr) or np.isnan(recent_corr):
                continue

            delta = recent_corr - baseline_corr
            label = f"{sym_a}|{sym_b}"
            results[label] = {
                "baseline_correlation": round(baseline_corr, 4),
                "recent_correlation": round(recent_corr, 4),
                "delta": round(delta, 4),
                "breakdown_detected": bool(abs(delta) > breakdown_threshold),
            }
    return results
