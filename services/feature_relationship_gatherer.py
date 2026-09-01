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

MAX_DECISIONS = 100_000


def gather_feature_relationship() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=MAX_DECISIONS)

    feature_ic = compute_feature_ic(closed_trades)
    redundancy = compute_feature_redundancy(closed_trades)
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
