"""Faz 244-246: Predictive Risk — Regime-Switching Monte Carlo.

Fikir: mevcut risk sistemi (RiskTargetStage/RiskGateStage) statik,
sabit kurallı limitler kullanıyor (ATR-tabanlı stop, max pozisyon boyutu
vb.) — hiçbiri "şu an açılacak bu işlem, MEVCUT piyasa rejiminde yakın
vadede ciddi bir seri kayba yol açar mı" sorusunu SORMUYOR. Bu modül
bunu, icat edilmiş bir olasılık dağılımı (ör. Gaussian) VARSAYMADAN,
doğrudan GERÇEK geçmiş kapanmış işlemlerin rejime göre koşullanmış
yüzde getiri dağılımından bootstrap örneklemesiyle simüle ediyor —
"regime-switching" burada bir stokastik diferansiyel denklem değil,
rejimin GERÇEKTEN o an ne olduğuna göre hangi geçmiş dağılımın
kullanılacağının seçilmesi anlamına geliyor."""
import numpy as np

MIN_REGIME_SAMPLES = 20


def load_regime_conditioned_pnl_pct(regime: str, limit: int = 2000) -> list[float]:
    """GERÇEK kapanmış işlemlerden (decisions.market_regime — Faz 244
    migration'ı ile eklendi, sadece bundan sonraki kapanışlar için
    dolu), her işlemin MARGIN'e göre yüzde getirisi. Kaldıraçlı
    işlemlerde margin = (entry_price*quantity)/leverage — kelly_sizing.py'
    nin ROI düzeltmesiyle (Faz 268g) AYNI mantık, ham $ pnl değil."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(text("""
            SELECT pnl, entry_price, quantity, leverage
            FROM decisions
            WHERE status = 'closed' AND excluded_from_stats = false
                AND market_regime = :regime
                AND pnl IS NOT NULL AND entry_price IS NOT NULL AND quantity IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT :limit
        """), {"regime": regime, "limit": limit}).fetchall()

    pct_returns = []
    for pnl, entry_price, quantity, leverage in rows:
        lev = leverage if leverage and leverage > 0 else 1.0
        margin = (float(entry_price) * float(quantity)) / lev
        if margin > 0:
            pct_returns.append(float(pnl) / margin)
    return pct_returns


def simulate_regime_drawdown_risk(
    pct_returns: list[float],
    horizon_trades: int = 10,
    num_simulations: int = 2000,
    ruin_threshold_pct: float = -0.20,
    seed: int | None = None,
) -> dict:
    """GERÇEK geçmiş yüzde getirilerinden (tekrarlı bootstrap örnekleme —
    parametrik bir dağılım varsayılmıyor) horizon_trades ardışık işlemlik
    num_simulations yol simüle edilir. Ardışık %getiriler bileşik
    (çarpımsal) birikir — tek tek toplanmıyor, gerçek bileşik getiri
    matematiğiyle tutarlı. breach_probability: bu yollardan kaçının,
    işlem dizisi boyunca herhangi bir noktada kümülatif kaybın
    ruin_threshold_pct'i aştığı (fail-closed: örneklem yetersizse None —
    icat edilmiş bir olasılık asla üretilmez)."""
    if len(pct_returns) < MIN_REGIME_SAMPLES:
        return {
            "sample_count": len(pct_returns),
            "breach_probability": None,
            "worst_case_5th_percentile": None,
            "median_terminal_return": None,
        }

    rng = np.random.default_rng(seed)
    returns_array = np.array(pct_returns)

    terminal_returns = np.empty(num_simulations)
    breaches = 0
    for i in range(num_simulations):
        path_returns = rng.choice(returns_array, size=horizon_trades, replace=True)
        cumulative = np.cumprod(1.0 + path_returns)
        if (np.min(cumulative) - 1.0) <= ruin_threshold_pct:
            breaches += 1
        terminal_returns[i] = cumulative[-1] - 1.0

    return {
        "sample_count": len(pct_returns),
        "breach_probability": breaches / num_simulations,
        "worst_case_5th_percentile": float(np.percentile(terminal_returns, 5)),
        "median_terminal_return": float(np.percentile(terminal_returns, 50)),
    }
