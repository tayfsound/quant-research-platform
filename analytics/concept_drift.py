"""Online Learning ve Concept Drift — Faz 719-743 (Cognitive Core 2.0 / M9).

analytics/model_drift.py FEATURE dağılımlarındaki (P(X)) kaymayı
(PSI/KS-test) tespit ediyor — ama bu, feature İLE SONUÇ arasındaki
İLİŞKİNİN (P(Y|X), "concept") değiştiğini YAKALAMAZ: aynı RSI değeri dün
"al" sinyaliydi, bugün piyasa rejimi değiştiği için "sat" sinyaline
dönüşmüş olabilir — feature'ın kendisi hiç kaymamış olsa bile. Bu modül,
standart bir istatistiksel test (2x2 ki-kare bağımsızlık testi) ile bir
ajanın/modelin GERÇEK doğruluk oranının iki zaman penceresi arasında
anlamlı şekilde değişip değişmediğini tespit ediyor — icat edilmiş bir
eşik değil.

Kasıtlı olarak SADECE tespit/rapor — hiçbir ajan ağırlığını/kararını
burada otomatik değiştirmiyor."""
from scipy import stats

MIN_SAMPLE_SIZE = 20
SIGNIFICANCE_LEVEL = 0.05


def compute_concept_drift(
    baseline_outcomes: list[bool],
    recent_outcomes: list[bool],
) -> dict | None:
    """baseline_outcomes/recent_outcomes: GERÇEK win/loss (True/False)
    sonuçları, iki AYRI zaman penceresinden (ör. bir ajanın 200 işlem
    önceki ve son 50 işlemdeki gerçek doğruluğu). 2x2 ki-kare bağımsızlık
    testiyle doğruluk oranının anlamlı şekilde değişip değişmediğini
    kontrol eder. <MIN_SAMPLE_SIZE her iki pencerede de olmalı; testin
    matematiksel olarak tanımsız kaldığı dejenere durumlarda (ör. bir
    hücre grubu sürekli sıfır) fail-closed None döner — icat edilmiş bir
    p-value asla üretilmez."""
    if len(baseline_outcomes) < MIN_SAMPLE_SIZE or len(recent_outcomes) < MIN_SAMPLE_SIZE:
        return None

    baseline_wins = sum(baseline_outcomes)
    baseline_losses = len(baseline_outcomes) - baseline_wins
    recent_wins = sum(recent_outcomes)
    recent_losses = len(recent_outcomes) - recent_wins

    contingency = [[baseline_wins, baseline_losses], [recent_wins, recent_losses]]
    try:
        _, p_value, _, _ = stats.chi2_contingency(contingency)
    except ValueError:
        return None

    return {
        "baseline_win_rate": round(baseline_wins / len(baseline_outcomes), 4),
        "recent_win_rate": round(recent_wins / len(recent_outcomes), 4),
        "p_value": round(float(p_value), 6),
        "drift_detected": bool(p_value < SIGNIFICANCE_LEVEL),
        "baseline_sample_size": len(baseline_outcomes),
        "recent_sample_size": len(recent_outcomes),
    }
