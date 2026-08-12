"""Model Drift Detection — proaktif PSI/KS-test.

analytics/feature_ic.py "bu sinyal HÂLÂ öngörücü mü" sorusunu (katkı vs
gerçekleşen getiri korelasyonu) soruyordu. Bu modül FARKLI bir soru
soruyor: "bu sinyalin KENDİ DAĞILIMI değişti mi" — piyasa rejimi kaymışsa
(ör. volatilite rejimi, trend karakteri) ya da bir veri/hesaplama hatası
feature'ın davranışını bozmuşsa, PnL gözle görülür şekilde bozulmadan
ÖNCE proaktif bir erken uyarı verebilir. İkisi tamamlayıcı: IC "hâlâ işe
yarıyor mu", drift "hâlâ aynı koşullarda mı çalışıyoruz".

Veri kaynağı: decisions.agent_contributions içindeki market_snapshot
zarfının features dict'i — ctx.market.features'ın GERÇEK, ham anlık
görüntüsü, HER decision'da (WAIT/red dahil) kaydediliyor — feature_ic.py
gibi sadece kapanmış işlemlerle sınırlı değil, çok daha yoğun bir
örneklem.

Kasıtlı olarak SADECE ölçüm/raporlama katmanı — hiçbir eşik/parametreyi
otomatik değiştirmiyor, bir insanın gerçek PSI/KS sayılarına bakıp karar
vermesi için (bu oturumun tekrarlanan ilkesi)."""
from collections import defaultdict

import numpy as np
from scipy import stats

MIN_WINDOW_SIZE = 30
# Endüstri standardı eşik (kredi skorlama/risk modellerinde yaygın):
# PSI<0.1 önemsiz, 0.1-0.25 orta, >=0.25 anlamlı bir dağılım kayması.
PSI_DRIFT_THRESHOLD = 0.25


def _extract_feature_series(decisions: list[dict]) -> dict[str, list[float]]:
    series: dict[str, list[float]] = defaultdict(list)
    for d in decisions:
        contributions = d.get("agent_contributions") or []
        for item in contributions:
            if not isinstance(item, dict) or item.get("type") != "market_snapshot":
                continue
            features = (item.get("data") or {}).get("features") or {}
            for name, value in features.items():
                # Sadece sayısal (sürekli/ordinal) feature'lar — kategorik
                # olanlar (trend="bullish" gibi) PSI/KS'in kapsamı dışında,
                # icat edilmiş bir sayısal dönüşüm uygulanmıyor.
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                series[name].append(float(value))
            break  # her decision'da market_snapshot en fazla bir kez var
    return series


def _psi(baseline: np.ndarray, recent: np.ndarray, bins: int = 10) -> float:
    """Standart PSI: baseline'ın kendi kotalarından (quantile) bin
    sınırları çıkarılır, iki dağılımın bu sabit binlerdeki oranları
    karşılaştırılır. Baseline neredeyse sabitse (anlamlı bin çıkmıyorsa)
    0.0 — icat edilmiş bir sayı üretilmez."""
    edges = np.unique(np.quantile(baseline, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges = edges.copy()
    edges[0], edges[-1] = -np.inf, np.inf
    baseline_counts, _ = np.histogram(baseline, bins=edges)
    recent_counts, _ = np.histogram(recent, bins=edges)
    baseline_pct = np.clip(baseline_counts / len(baseline), 1e-4, None)
    recent_pct = np.clip(recent_counts / len(recent), 1e-4, None)
    return float(np.sum((recent_pct - baseline_pct) * np.log(recent_pct / baseline_pct)))


def compute_feature_drift(
    decisions: list[dict], split_frac: float = 0.5, min_window_size: int = MIN_WINDOW_SIZE,
) -> dict[str, dict]:
    """decisions: DecisionPersistor.list_recent()'in döndürdüğü, EN
    YENİDEN EN ESKİYE sıralı satırlar. Kronolojik sıraya çevrilip
    split_frac ile ikiye bölünüyor: ilk yarı (ESKİ) = baseline, ikinci
    yarı (YENİ) = recent — "şu an, geçmişe göre" karşılaştırması.

    Dönen dict: {feature_name: {"psi", "ks_statistic", "ks_p_value",
    "baseline_n", "recent_n", "drift_detected"}}. min_window_size altında
    kalan ya da baseline'da gerçek çeşitlilik olmayan feature'lar hiç
    dönmüyor — fail-closed, istatistiksel olarak anlamsız bir sayı asla
    raporlanmaz."""
    chronological = list(reversed(decisions))
    split_idx = int(len(chronological) * split_frac)
    baseline_decisions = chronological[:split_idx]
    recent_decisions = chronological[split_idx:]

    baseline_series = _extract_feature_series(baseline_decisions)
    recent_series = _extract_feature_series(recent_decisions)

    results: dict[str, dict] = {}
    for name, baseline_values in baseline_series.items():
        if name not in recent_series:
            continue
        baseline = np.array(baseline_values)
        recent = np.array(recent_series[name])
        if len(baseline) < min_window_size or len(recent) < min_window_size:
            continue
        if len(set(baseline.tolist())) < 2:
            continue

        psi = _psi(baseline, recent)
        ks_stat, ks_p = stats.ks_2samp(baseline, recent)

        results[name] = {
            "psi": round(psi, 4),
            "ks_statistic": round(float(ks_stat), 4),
            "ks_p_value": round(float(ks_p), 4),
            "baseline_n": len(baseline),
            "recent_n": len(recent),
            "drift_detected": psi >= PSI_DRIFT_THRESHOLD,
        }
    return results
