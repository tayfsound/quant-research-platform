"""Faz 268-sonrası: Cross-Symbol Correlation Filter.

Gerçek bulgu: services/portfolio_fusion.py (risk/limits/portfolio.py'nin
gerçek kovaryans matrisiyle) zaten aynı anda önerilen sembollerin pozisyon
BÜYÜKLÜĞÜNÜ (dolar riskini) küçültüyordu — ama council'in kendi
CONVICTION'ı (confidence) hiç etkilenmiyordu. 3 sembol aynı anda aynı
yönde önerildiğinde, bunlar birbirine yüksek korele olsa bile (aynı
temel piyasa beta'sının 3 farklı yansıması — 3 bağımsız kanıt DEĞİL)
council bunu hiç fark etmiyordu. Bu, services/belief_engine.py'nin TEK
bir sembolün kendi ajanları arasında zaten yaptığı crowding_penalty/
cluster_balance mantığının AYNISI — burada sembol düzeyine taşınıyor."""
import numpy as np

HIGH_CORRELATION_THRESHOLD = 0.7
MIN_CLUSTER_PEERS = 1  # aynı yönde en az 1 diğer yüksek-korele sembol
MAX_CONVICTION_DISCOUNT = 0.5  # en fazla %50 confidence indirimi


def compute_same_direction_correlation_discount(
    returns: dict[str, list[float]],
    directions: dict[str, str],
) -> dict[str, float]:
    """returns: {symbol: [gerçek dönemsel getiri, ...]} (hepsi AYNI
    uzunlukta — çağıran taraf zaten hizalıyor, bkz. services/orchestrator.
    py::_apply_portfolio_fusion). directions: {symbol: "LONG"|"SHORT"}.

    Her sembol için, KENDİ yönünde AYNI ANDA önerilen diğer sembollerle
    olan GERÇEK EN YÜKSEK (ortalama değil — tek bir yüksek-korele eş bile
    gerçek bir redundant-risk kanıtı; başka, korelasyonsuz bir eşin
    varlığı bunu "seyreltmemeli") korelasyona göre [1-MAX_CONVICTION_
    DISCOUNT, 1.0] aralığında bir confidence çarpanı döner. Sadece yüksek
    korelasyonlu (>HIGH_CORRELATION_THRESHOLD), en az bir eş sembollü
    aynı-yönlü bir küme varsa indirim uygular — asla büyütmez, fail-closed."""
    symbols = list(returns.keys())
    if len(symbols) < 2:
        return {s: 1.0 for s in symbols}

    matrix = np.array([returns[s] for s in symbols])
    with np.errstate(invalid="ignore"):
        corr = np.corrcoef(matrix)

    multipliers: dict[str, float] = {}
    for i, sym in enumerate(symbols):
        same_direction_corrs = [
            corr[i, j] for j, other in enumerate(symbols)
            if other != sym and directions.get(other) == directions.get(sym)
            and not np.isnan(corr[i, j])
        ]
        if len(same_direction_corrs) < MIN_CLUSTER_PEERS:
            multipliers[sym] = 1.0
            continue

        max_corr = float(np.max(same_direction_corrs))
        if max_corr <= HIGH_CORRELATION_THRESHOLD:
            multipliers[sym] = 1.0
            continue

        excess = (max_corr - HIGH_CORRELATION_THRESHOLD) / (1.0 - HIGH_CORRELATION_THRESHOLD)
        excess = min(max(excess, 0.0), 1.0)
        multipliers[sym] = 1.0 - excess * MAX_CONVICTION_DISCOUNT

    return multipliers
