"""Measurement Stability Summary — Faz 415 (2026-09-06). Kullanıcı isteği:
"son eklediğimiz modüllerden aldığımız verilerin zaman içindeki
tutarlılığını gösteren verileri dashboard'da göremiyorum." Faz 407
(compute_stability) kasıtlı olarak backend-only kalmıştı — hiçbir
dashboard görünümü kapsamda değildi. Bu gatherer YENİ bir hesaplama
yapmıyor: services/research_summary_gatherer.py'nin zaten paralel/canlı
çektiği modülleri (ve ayrıca research-summary listesinde olmayan
korelasyon + feature IC'yi, kendi persist edilmiş en son anlık
görüntülerinden — YENİDEN hesaplamadan) tarayıp analytics/measurement_
stability.py::extract_stability_summary() ile düz bir listeye indiriyor."""
from analytics.measurement_stability import extract_stability_summary
from services.research_summary_gatherer import gather_research_summary


def _correlation_module_entry() -> dict:
    from database.repositories.correlation_report_repository import CorrelationReportRepository
    from database.session_factory import SessionFactory

    try:
        with SessionFactory.get_session() as session:
            latest = CorrelationReportRepository(session).get_latest()
        if latest is None:
            return {"key": "correlation", "label": "Sembol Korelasyonu", "fields": [], "n_fields": 0, "last_computed_at": None, "error": None}
        fields = extract_stability_summary(latest.get("result"))
        return {
            "key": "correlation", "label": "Sembol Korelasyonu", "fields": fields, "n_fields": len(fields),
            "last_computed_at": latest.get("created_at"), "error": None,
        }
    except Exception as exc:
        return {"key": "correlation", "label": "Sembol Korelasyonu", "fields": [], "n_fields": 0, "last_computed_at": None, "error": str(exc)}


def _feature_ic_module_entry() -> dict:
    from database.repositories.feature_ic_report_repository import FeatureICReportRepository
    from database.session_factory import SessionFactory

    try:
        with SessionFactory.get_session() as session:
            latest = FeatureICReportRepository(session).get_latest()
        if latest is None:
            return {"key": "feature_ic", "label": "Feature IC", "fields": [], "n_fields": 0, "last_computed_at": None, "error": None}
        fields = extract_stability_summary(latest.get("features"))
        return {
            "key": "feature_ic", "label": "Feature IC", "fields": fields, "n_fields": len(fields),
            "last_computed_at": latest.get("created_at"), "error": None,
        }
    except Exception as exc:
        return {"key": "feature_ic", "label": "Feature IC", "fields": [], "n_fields": 0, "last_computed_at": None, "error": str(exc)}


def gather_measurement_stability_summary() -> dict:
    modules = []
    for entry in gather_research_summary()["modules"]:
        if entry["error"] is not None:
            modules.append({"key": entry["key"], "label": entry["label"], "fields": [], "n_fields": 0, "last_computed_at": None, "error": entry["error"]})
            continue
        fields = extract_stability_summary(entry["result"])
        modules.append({"key": entry["key"], "label": entry["label"], "fields": fields, "n_fields": len(fields), "last_computed_at": None, "error": None})

    modules.append(_correlation_module_entry())
    modules.append(_feature_ic_module_entry())

    # Faz 415 — en dikkat çekici (en oynak) alanlar tek bakışta görünsün:
    # tüm modüllerin tüm alanları CV'ye göre azalan sıralanıp ilk 15'i
    # "en oynak" olarak öne çıkarılıyor. min_sample=5 — çok az geçmişe
    # (n<5) dayanan bir CV, "en oynak" listesinde yanıltıcı bir kesinlik
    # izlenimi vermesin (icat edilmiş bir güven asla).
    all_fields = []
    for m in modules:
        for f in m["fields"]:
            if f.get("n", 0) >= 5 and f.get("coefficient_of_variation") is not None:
                all_fields.append({"module_key": m["key"], "module_label": m["label"], **f})
    most_volatile = sorted(all_fields, key=lambda f: -f["coefficient_of_variation"])[:15]

    return {"modules": modules, "most_volatile": most_volatile}
