"""Meta-Learning ve Self-Improving Intelligence — Faz 744-768
(Cognitive Core 2.0 / M10).

meta_optimizer/agent_tuner.py (CMA-ES) her onaylı tuning turunda
in_sample_sharpe/mean_oos_sharpe_tuned/mean_oos_sharpe_baseline/
sharpe_improvement kaydediyor (database/repositories'in
agent_tuning_approvals tablosu) — ama bu turların ZAMAN İÇİNDE GERÇEKTEN
bir iyileşme trendi mi gösterdiği yoksa rastgele mi dağıldığı hiç analiz
edilmiyordu: meta-öğrenme sürecinin kendisi "self-improving" mi, yoksa
sadece gürültü mü ürettiği bilinmiyordu.

compute_meta_learning_trend(): standart, parametrik olmayan bir trend
testi (Spearman rank korelasyonu — tekil aykırı bir turdan Pearson'a göre
daha az etkilenir) ile tur sırası ile sharpe_improvement arasındaki
ilişkiyi ölçüyor. İcat edilmiş bir "öğrenme skoru" değil.

Kasıtlı olarak SADECE tespit/rapor — hiçbir tuning kararını burada
otomatik onaylamıyor/uygulamıyor."""
from scipy import stats

MIN_ROUNDS = 8
SIGNIFICANCE_LEVEL = 0.05


def compute_meta_learning_trend(sharpe_improvements: list[float]) -> dict | None:
    """sharpe_improvements: KRONOLOJIK sırayla (en eski turdan en yeniye),
    GERÇEK onaylı tuning turlarının sharpe_improvement değerleri.
    Spearman korelasyonu (tur sırası vs sharpe_improvement) hesaplar —
    pozitif ve anlamlıysa meta-öğrenme süreci GERÇEKTEN zamanla
    iyileşiyor demektir; negatif ve anlamlıysa KÖTÜLEŞİYOR (ör.
    overfitting biriktiriyor) demektir. <MIN_ROUNDS turla fail-closed
    None döner — az sayıda turdan bir trend icat edilmez."""
    if len(sharpe_improvements) < MIN_ROUNDS:
        return None

    round_order = list(range(len(sharpe_improvements)))
    correlation, p_value = stats.spearmanr(round_order, sharpe_improvements)
    if correlation is None or (hasattr(correlation, "__len__")):
        return None

    correlation = float(correlation)
    p_value = float(p_value)
    if correlation != correlation or p_value != p_value:  # NaN kontrolü (ör. sabit seri)
        return None

    is_significant = p_value < SIGNIFICANCE_LEVEL
    if is_significant and correlation > 0:
        trend = "improving"
    elif is_significant and correlation < 0:
        trend = "degrading"
    else:
        trend = "no_significant_trend"

    return {
        "spearman_correlation": round(correlation, 4),
        "p_value": round(p_value, 6),
        "trend": trend,
        "n_rounds": len(sharpe_improvements),
        "avg_sharpe_improvement": round(sum(sharpe_improvements) / len(sharpe_improvements), 6),
    }
