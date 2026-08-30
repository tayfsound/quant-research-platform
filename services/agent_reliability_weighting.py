"""Faz 381 — kullanıcı bulgusu (PYPLUSDT LONG %65.7 kararının detaylı
incelemesi, sonra sistem genelinde doğrulandı: 642 karardan hiçbiri
pozisyon açmadı): "Agent reliability ve agent influence çok sıkı bağlı —
son dönem güvenilirlik uncertainty artırıcı/ağırlık azaltıcı bir sinyal
olmalı, hard suppression mekanizması değil."

Eski davranış: performance_weight, benching floor'u (MIN_INFLUENCE=0.1,
DÜZ bir taban — eşiğin az altındaki bir ajan ile katastrofik derecede
kötü bir ajan AYNI floor'a düşer) ve unanswered-debate-challenge
cezalarını SIRALI ÇARPIM olarak birleştiriyordu. Tek tek makul görünen
çarpanlar (0.1 × 0.7 × ...) birlikte aşırı küçük bir sonuca ulaşıyordu.

Yeni model: her bastırma kaynağı bir "uncertainty" katkısına (odds-uzayı,
p/(1-p)) çevrilir, kaynaklar ÇARPILMAK yerine TOPLANIR, sonra
1/(1+toplam_uncertainty) ile tek bir sınırlı ([0,1]) ağırlığa dönüştürülür.
Bu dönüşümün kritik özelliği: TEK bir kaynak için eskisiyle TAM AYNI
sonucu verir (bkz. tests/test_agent_reliability_weighting.py), ama BİRDEN
FAZLA kaynak birleştiğinde üstel çöküş yerine kademeli birleşir — "az
güvenilmez" ile "çok güvenilmez" artık ayrışıyor, "gerçekten kötü" ajanlar
hâlâ güçlü şekilde susturuluyor."""


def _uncertainty_contribution(p: float) -> float:
    p = min(max(p, 0.0), 0.999)
    return p / (1.0 - p)


# source_reliability=0 (deficit_ratio=1.0) iken eski MIN_INFLUENCE=0.1 ile
# pratik olarak eşleşecek şekilde kalibre edildi: 1/(1+0.9/(1-0.9)) = 0.1.
MAX_BENCH_PENALTY = 0.9


def compute_reliability_uncertainty(source_reliability: float, bench_threshold: float, benched: bool) -> float:
    """Benched değilse 0.0 — histerezis KARARI (ne zaman güvenilmeyeceği)
    burada değişmiyor, sadece güvenilmediğinde ne kadar bastırılacağı."""
    if not benched or bench_threshold <= 0:
        return 0.0
    deficit_ratio = max(0.0, bench_threshold - source_reliability) / bench_threshold
    return _uncertainty_contribution(min(deficit_ratio, 1.0) * MAX_BENCH_PENALTY)


def compute_challenge_uncertainty(per_challenge_penalties: list[float]) -> float:
    return sum(_uncertainty_contribution(p) for p in per_challenge_penalties)


def compute_performance_weight(
    reliability_uncertainty: float, challenge_uncertainty: float, moe_tilt: float = 1.0,
) -> float:
    """MoE regime tilt bilinçli olarak bu modelin DIŞINDA, ayrı bir çarpan
    olarak kalıyor — tek yönlü bir güvensizlik sinyali değil, iki yönlü
    (elverişli rejimde büyütebilen de) bir "rejime uygunluk" sinyali."""
    suppression_weight = 1.0 / (1.0 + reliability_uncertainty + challenge_uncertainty)
    return round(suppression_weight * moe_tilt, 4)
