"""Collective Intelligence'ın girdisini GERÇEK AgentMemory geçmişinden
toplayan tek kaynak — Cognitive Core 10.0. analytics/collective_
intelligence.py::compute_expected_majority_accuracy() saf (pure) kalıyor
— gerçek veriye dokunan kod burada.

10 gerçek yönlü-oy-veren ajanın (contracts/agent.py::VOTING_AGENT_
DOMAINS) her biri için AgentMemory'nin GERÇEK, son 20 kararlık isabet
oranı (services/source_reliability_agent.py'nin kullandığı AYNI WINDOW,
AYNI MIN_SAMPLES eşiği — tek gerçek kaynak) toplanır; yeterli örneklemi
olmayan bir ajan (WAIT-only time/epistemology dahil, hiç yönlü oy
vermedikleri için total_predictions=0 kalır) hesaba dahil edilmez —
icat edilmiş bir "%50 varsayılan" asla kullanılmaz."""
from analytics.collective_intelligence import (
    compute_accuracy_confidence_interval,
    compute_expected_majority_accuracy,
)
from contracts.agent import VOTING_AGENT_DOMAINS
from services.agent_memory import AgentMemory

WINDOW = 20
MIN_SAMPLES = 10


def gather_collective_intelligence() -> dict:
    memory = AgentMemory()

    per_agent_accuracy: dict[str, float] = {}
    per_agent_sample_size: dict[str, int] = {}
    per_agent_confidence_interval: dict[str, dict] = {}
    excluded_insufficient_data: list[str] = []

    for domain in sorted(d.value for d in VOTING_AGENT_DOMAINS):
        summary = memory.get_summary(domain, window=WINDOW)
        if summary.total_predictions >= MIN_SAMPLES:
            per_agent_accuracy[domain] = summary.recent_accuracy
            per_agent_sample_size[domain] = summary.total_predictions
            # Faz 303 — n=20'de nokta tahmini tek başına yanıltıcı
            # olabiliyor (bkz. analytics/collective_intelligence.py::
            # compute_accuracy_confidence_interval yorumu) — Wilson
            # aralığı bilgilendirme amaçlı ekleniyor, hiçbir hesabı
            # değiştirmiyor.
            correct = round(summary.recent_accuracy * summary.total_predictions)
            ci = compute_accuracy_confidence_interval(correct, summary.total_predictions)
            if ci is not None:
                per_agent_confidence_interval[domain] = ci
        else:
            excluded_insufficient_data.append(domain)

    accuracies = list(per_agent_accuracy.values())
    condorcet = compute_expected_majority_accuracy(accuracies) if len(accuracies) >= 2 else None

    return {
        "per_agent_accuracy": per_agent_accuracy,
        "per_agent_sample_size": per_agent_sample_size,
        "per_agent_confidence_interval": per_agent_confidence_interval,
        "agents_included": list(per_agent_accuracy.keys()),
        "agents_excluded_insufficient_data": excluded_insufficient_data,
        "condorcet": condorcet,
    }
