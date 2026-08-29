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
    """Faz 369-devam — GPT dış rapor önerisi: "Brier score'u out-of-sample
    hesaplıyor musunuz? Aynı veri hem confidence üretmek hem Brier ölçmek
    için kullanılıyorsa şişmiş olabilir." Gerçek bulgu (bkz. contracts/
    agent.py::AgentOpinion.raw_confidence): mevcut brier_score HER ZAMAN
    KALİBRE EDİLMİŞ confidence'tan hesaplanıyordu — ham sinyalin kendisi
    ne kadar iyi, kalibrasyon bunu ne kadar düzeltiyor ayırt edilemiyordu.

    Her domain için artık İKİ Brier skoru: mevcut `brier_score` (kalibre
    edilmiş, davranış DEĞİŞMEDİ) ve yeni `raw_brier_score` (kalibrasyon
    ÖNCESİ ham confidence'tan — SADECE raw_confidence alanı eklendikten
    SONRAKİ yeni kararlarda dolu, yeterli örneklem birikene kadar None,
    icat edilmiş bir sayı asla üretilmez)."""
    memory = agent_memory or AgentMemory()
    cutoff = get_reliability_legacy_cutoff()

    by_domain: dict[str, dict] = {}
    for domain in sorted(d.value for d in VOTING_AGENT_DOMAINS):
        records = memory.get_filtered_records(domain, min_timestamp=cutoff)
        predictions = [(r.confidence, r.was_correct) for r in records if r.confidence is not None]
        score = compute_brier_score(predictions)
        if score is None:
            continue
        raw_predictions = [(r.raw_confidence, r.was_correct) for r in records if r.raw_confidence is not None]
        score["raw_brier_score"] = compute_brier_score(raw_predictions)
        by_domain[domain] = score

    return {"by_domain": by_domain}
