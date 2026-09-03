"""Direction Prediction v2'nin girdisini GERÇEK ajan tahmin-sonuç
çiftlerinden toplayan tek kaynak — Cognitive Core 2.0 / M4 (Faz 519-543).
analytics/direction_prediction_v2.py::compute_brier_score() saf (pure)
kalıyor — gerçek veriye dokunan kod burada.

AgentMemory'nin zaten sakladığı (confidence, was_correct) çiftleri
doğrudan kullanılıyor — services/confidence_calibration.py'nin ECE
hesabıyla AYNI veri kaynağı, ayrı bir sorgu icat edilmiyor."""
from analytics.direction_prediction_v2 import compute_brier_score
from analytics.measurement_stability import compute_stability
from contracts.agent import VOTING_AGENT_DOMAINS
from services.agent_memory import AgentMemory, get_reliability_legacy_cutoff

STABILITY_LOOKBACK_SNAPSHOTS = 12


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

    from database.repositories.direction_prediction_v2_report_repository import (
        DirectionPredictionV2ReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        past_snapshots = DirectionPredictionV2ReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)
    past_by_domain: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for domain, score in ((snap.get("result") or {}).get("by_domain") or {}).items():
            past_by_domain.setdefault(domain, []).append(score.get("brier_score"))

    by_domain: dict[str, dict] = {}
    for domain in sorted(d.value for d in VOTING_AGENT_DOMAINS):
        records = memory.get_filtered_records(domain, min_timestamp=cutoff)
        predictions = [(r.confidence, r.was_correct) for r in records if r.confidence is not None]
        score = compute_brier_score(predictions)
        if score is None:
            continue
        raw_predictions = [(r.raw_confidence, r.was_correct) for r in records if r.raw_confidence is not None]
        score["raw_brier_score"] = compute_brier_score(raw_predictions)
        # Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
        # içindeki stabilitesini de ölçelim." SADECE gözlem.
        score["brier_score_stability"] = compute_stability([*past_by_domain.get(domain, []), score["brier_score"]])
        by_domain[domain] = score

    return {"by_domain": by_domain}
