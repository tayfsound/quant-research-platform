"""Portfolio Intelligence — Faz 644-668 (Cognitive Core 2.0 / M6).

Mevcut PortfolioRiskEngine (risk/limits/portfolio.py) portföyün toplam
VaR'ını ölçüyor ama "gerçekte kaç BAĞIMSIZ bahis yapıyoruz" sorusuna hiç
cevap vermiyor — 10 pozisyon açık olsa bile, hepsi %90 korele ise bu
GERÇEKTE ~1-2 bağımsız bahis kadar riskli (risk/cross_symbol_correlation.py
bunu TEK bir cycle'daki AYNI-YÖNLÜ sembollere confidence indirimi olarak
uyguluyor, ama portföyün GENEL çeşitlendirme kalitesini tek bir sayıyla
özetleyen bir metrik yoktu). Bu modül standart bir portföy-teorisi
kavramı olan Effective Number of Bets'i (ENB) ekliyor — icat edilmiş bir
çeşitlendirme ölçüsü değil.

ENB = 1 / (w' Σ w), Σ = korelasyon matrisi, w = normalize edilmiş mutlak
ağırlıklar. Tüm pozisyonlar korelasyonsuzsa ENB ≈ pozisyon sayısı; tam
korele ise ENB ≈ 1 (tek bir bahis gibi davranıyorlar).

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon büyüklüğü kararını
burada otomatik değiştirmiyor."""
import numpy as np

MIN_SYMBOLS = 2
MIN_RETURN_HISTORY = 10


def compute_effective_number_of_bets(
    weights: dict[str, float],
    returns: dict[str, list[float]],
) -> dict | None:
    """weights: {symbol: pozisyon ağırlığı} (mutlak değeri önemli, işaret
    değil) — normalize ediliyor. returns: {symbol: GERÇEK dönemsel getiri
    serisi}, weights'teki her sembol için AYNI uzunlukta olmalı.
    <MIN_SYMBOLS sembol, yetersiz/uzunluk-uyuşmayan getiri geçmişi ya da
    sıfır toplam ağırlıkla fail-closed None döner."""
    symbols = [s for s in weights if s in returns]
    if len(symbols) < MIN_SYMBOLS:
        return None

    lengths = {len(returns[s]) for s in symbols}
    if len(lengths) != 1 or min(lengths) < MIN_RETURN_HISTORY:
        return None

    abs_weights = np.array([abs(weights[s]) for s in symbols])
    total = abs_weights.sum()
    if total <= 0:
        return None
    w = abs_weights / total

    matrix = np.array([returns[s] for s in symbols])
    with np.errstate(invalid="ignore"):
        corr = np.corrcoef(matrix)
    if np.any(np.isnan(corr)):
        return None

    portfolio_variance_proxy = float(w @ corr @ w)
    if portfolio_variance_proxy <= 0:
        return None

    enb = 1.0 / portfolio_variance_proxy
    return {
        "effective_number_of_bets": round(enb, 4),
        "position_count": len(symbols),
        "diversification_ratio": round(enb / len(symbols), 4),
    }
