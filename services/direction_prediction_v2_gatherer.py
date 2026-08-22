"""Direction Prediction v2'nin girdisini GERÇEK ajan tahmin-sonuç
çiftlerinden toplayan tek kaynak — Cognitive Core 2.0 / M4 (Faz 519-543).
analytics/direction_prediction_v2.py::compute_brier_score() saf (pure)
kalıyor — gerçek veriye dokunan kod burada.

AgentMemory'nin zaten sakladığı (confidence, was_correct) çiftleri
doğrudan kullanılıyor — services/confidence_calibration.py'nin ECE
hesabıyla AYNI veri kaynağı, ayrı bir sorgu icat edilmiyor."""
from analytics.direction_prediction_v2 import compute_brier_score
from contracts.agent import VOTING_AGENT_DOMAINS
from services.agent_memory import AgentMemory, get_reliability_legacy_cutoff


def gather_direction_prediction_v2(agent_memory: AgentMemory | None = None) -> dict:
    memory = agent_memory or AgentMemory()
    cutoff = get_reliability_legacy_cutoff()

    by_domain: dict[str, dict] = {}
    for domain in sorted(d.value for d in VOTING_AGENT_DOMAINS):
        records = memory.get_filtered_records(domain, min_timestamp=cutoff)
        predictions = [(r.confidence, r.was_correct) for r in records if r.confidence is not None]
        score = compute_brier_score(predictions)
        if score is not None:
            by_domain[domain] = score

    return {"by_domain": by_domain}
