"""Feature Relationship'ın girdisini GERÇEK kapanmış kararlardan toplayan
tek kaynak — Faz 368. analytics/feature_relationship.py saf kalıyor,
gerçek veriye dokunan kod burada (feature_ic_by_regime_gatherer.py'deki
AYNI 100_000-limit deseni)."""
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.feature_ic import compute_feature_ic
from analytics.feature_relationship import (
    compute_conditional_ic,
    compute_feature_redundancy,
    compute_multivariable_residualized_ic,
    compute_redundancy_clusters,
)
from analytics.measurement_stability import compute_stability

MAX_DECISIONS = 100_000
STABILITY_LOOKBACK_SNAPSHOTS = 12


def _attach_redundancy_stability(redundancy: dict[str, dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." Kullanıcının FeatureIC.tsx
    redundancy grafiğini "kaotik" bulduğu gözlemle DOĞRUDAN ilgili —
    bir kenarın (feature çiftinin) gerçekten istikrarlı bir ilişki mi
    yoksa gürültü mü olduğunu SADECE gözlem olarak ekliyor."""
    past_by_pair: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for pair, stat in (snap.get("redundancy") or {}).items():
            past_by_pair.setdefault(pair, []).append(stat.get("correlation"))

    for pair, stat in redundancy.items():
        series = [*past_by_pair.get(pair, []), stat.get("correlation")]
        stat["correlation_stability"] = compute_stability(series)


def gather_feature_relationship() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.feature_relationship_report_repository import (
        FeatureRelationshipReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=MAX_DECISIONS)
        past_snapshots = FeatureRelationshipReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)

    feature_ic = compute_feature_ic(closed_trades)
    redundancy = compute_feature_redundancy(closed_trades)
    _attach_redundancy_stability(redundancy, past_snapshots)
    conditional_ic = compute_conditional_ic(closed_trades, redundancy, feature_ic)
    # Faz B (2026-08-29) — Faz A'nın SADECE ikili koşullandırmasının
    # ötesine geçen çoklu-değişkenli residualizasyon. compute_redundancy_
    # clusters zaten yüksek-redundant bulunan ÇİFTLERDEN bağlı bileşenler
    # kuruyor (kombinasyon patlaması riski YOK — GPT'nin kendi uyarısı,
    # tüm altkümeler taranmıyor, sadece Faz A'nın işaretlediği kümeler).
    clusters = compute_redundancy_clusters(redundancy)
    residualized_ic = compute_multivariable_residualized_ic(closed_trades, clusters)

    return {
        "redundancy": redundancy,
        "conditional_ic": conditional_ic,
        "redundancy_clusters": [sorted(c) for c in clusters],
        "residualized_ic": residualized_ic,
        "n_decisions_analyzed": len(closed_trades),
        "evaluation_window": describe_evaluation_window(closed_trades, limit=MAX_DECISIONS),
    }
