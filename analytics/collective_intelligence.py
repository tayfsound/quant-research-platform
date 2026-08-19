"""Collective Research Intelligence — Faz 971-1000 (Cognitive Core 10.0).

10-ajanlı council zaten bir "kolektif zeka" mimarisi ama toplamının,
GERÇEKTEN en iyi tekil ajandan daha isabetli olup olmadığı hiç
doğrulanmamıştı. Bu modül, Condorcet'in Jüri Teoremi'nin (1785) standart
kapalı-form sonucunu kullanıyor: her ajan bağımsız ve rastgeleden daha
iyiyse (accuracy>0.5), çoğunluk oyunun BEKLENEN doğruluğu HERHANGİ bir
tekil ajandan yüksek olmalı ve ajan sayısı arttıkça 1'e yakınsamalı —
icat edilmiş bir "kolektif zeka skoru" değil.

BAĞIMSIZLIK VARSAYIMI: bu hesap ajanların BAĞIMSIZ hata yaptığını
varsayıyor — gerçekte ne kadar bağımsız oldukları risk/cross_symbol_
correlation.py ve analytics/opportunity_quality.py::compute_agent_
agreement'ın ölçtüğü ayrı bir soru; yüksek ajan-arası korelasyon bu
teoremin öngördüğü avantajı GERÇEKTE zayıflatır.

Kasıtlı olarak SADECE değerlendirme/rapor — hiçbir ajan ağırlığını
otomatik değiştirmiyor."""
from itertools import product

from scipy.stats import binomtest

MIN_AGENTS = 2


def compute_expected_majority_accuracy(individual_accuracies: list[float]) -> dict | None:
    """individual_accuracies: her ajanın GERÇEK, ölçülmüş doğruluk oranı
    (ör. analytics/direction_prediction_v2.py::compute_brier_score'dan
    türetilmiş). Ajanların BAĞIMSIZ olduğu varsayımıyla, tam numaralandırma
    (brute-force, 2^n kombinasyon) ile çoğunluk oyunun beklenen doğruluğunu
    hesaplar. <MIN_AGENTS ajanla ya da [0,1] dışında bir olasılıkla
    fail-closed None döner."""
    n = len(individual_accuracies)
    if n < MIN_AGENTS or any(not (0.0 <= p <= 1.0) for p in individual_accuracies):
        return None

    majority_threshold = n / 2
    expected_majority_correct = 0.0
    for outcomes in product([True, False], repeat=n):
        prob = 1.0
        for is_correct, p in zip(outcomes, individual_accuracies):
            prob *= p if is_correct else (1 - p)
        n_correct = sum(outcomes)
        if n_correct > majority_threshold:
            expected_majority_correct += prob
        elif n_correct == majority_threshold:
            expected_majority_correct += prob * 0.5  # berabere -> yarı yarıya karar

    best_individual = max(individual_accuracies)
    return {
        "expected_majority_accuracy": round(expected_majority_correct, 6),
        "best_individual_accuracy": round(best_individual, 6),
        "collective_beats_best_individual": bool(expected_majority_correct > best_individual),
        "n_agents": n,
    }


def compute_accuracy_confidence_interval(
    correct: int, total: int, confidence_level: float = 0.95
) -> dict | None:
    """Faz 303 — dış rapor (GPT) + kullanıcının uzun süredir bekleyen
    bulgusu: sistemin birçok yerinde (bu modülün girdisi dahil) "son 20
    örneklem" doğruluk ORANI tek bir nokta tahmini olarak gösteriliyor,
    ama n=20'de bu oranın gerçek belirsizliği büyük — ör. 3/20 (%15) ile
    8/20 (%40) arasındaki fark, tek bir kararın sonucuyla değişebilecek
    kadar ince. Wilson skoru güven aralığı (binom oranları için standart,
    küçük n'de normal-yaklaşıklıklı basit formüllerden daha güvenilir)
    bu belirsizliği açık ediyor.

    Kasıtlı olarak SADECE bilgilendirme — hiçbir karar mantığını
    (ağırlıklandırma, benching, Condorcet hesabı) DEĞİŞTİRMİYOR, nokta
    tahminin (recent_accuracy) yanına eklenen ayrı bir alan."""
    if total <= 0 or not (0 <= correct <= total):
        return None
    ci = binomtest(correct, total).proportion_ci(confidence_level=confidence_level, method="wilson")
    return {
        "low": round(float(ci.low), 4),
        "high": round(float(ci.high), 4),
        "confidence_level": confidence_level,
    }
