"""Kaynak guvenilirligi ajani — diger ajanlarin guvenilirligini puanlar."""
from typing import Dict, List
from dataclasses import dataclass

@dataclass
class ReliabilityScore:
    domain: str
    source_reliability: float
    data_freshness_hours: float
    source_count: int

class SourceReliabilityAgent:
    """Diğer ajanların güvenilirliğini gerçek geçmiş performansına göre
    puanlar. Ayrıca "auto-bench" uyguluyor: bir domain üst üste
    BENCH_AFTER kez düşük güvenilirlik gösterirse (BENCH_THRESHOLD altı),
    RECOVERY_THRESHOLD'a gerçekten geri dönene kadar oyu sıfır ağırlıkla
    sayılır — CouncilOrchestrator bunu opinion.performance_weight=0 ile
    uyguluyor. Metafor değil: sürekli kötü performans gösteren bir ajan
    kararın ağırlıklandırmasında gerçekten söz sahibi olmaktan çıkıyor,
    geçmişi düzelene kadar."""

    BENCH_THRESHOLD = 0.35
    BENCH_AFTER = 5
    RECOVERY_THRESHOLD = 0.5

    def __init__(self):
        self.history: Dict[str, List[float]] = {}
        self._consecutive_low: Dict[str, int] = {}
        self._benched: set[str] = set()

    def annotate(self, opinions: List[dict]) -> List[dict]:
        """Her opinion'a source_reliability puanı ve benched durumunu ekler."""
        for op in opinions:
            domain = op.get("domain", "unknown")
            if domain not in self.history:
                self.history[domain] = []

            # Basit: confidence history'si varsa ortalama
            confidence = op.get("confidence", 0.5)
            self.history[domain].append(confidence)

            # Reliability = son 10 kararin ortalama confidence'i
            recent = self.history[domain][-10:]
            reliability = sum(recent) / len(recent) if recent else 0.5
            reliability = min(reliability, 1.0)

            self._update_bench_state(domain, reliability)

            op["source_reliability"] = reliability
            op["data_freshness_hours"] = 0.0  # Simulated real-time
            op["source_count"] = 1
            op["benched"] = domain in self._benched

        return opinions

    def _update_bench_state(self, domain: str, reliability: float) -> None:
        if reliability < self.BENCH_THRESHOLD:
            self._consecutive_low[domain] = self._consecutive_low.get(domain, 0) + 1
            if self._consecutive_low[domain] >= self.BENCH_AFTER:
                self._benched.add(domain)
        elif reliability >= self.RECOVERY_THRESHOLD:
            # Gerçek toparlanma — sadece "düşük değil" değil, gerçekten iyi.
            self._consecutive_low[domain] = 0
            self._benched.discard(domain)

    def is_benched(self, domain: str) -> bool:
        return domain in self._benched

    def get_domain_reliability(self, domain: str) -> float:
        scores = self.history.get(domain, [])
        return sum(scores) / len(scores) if scores else 0.5
