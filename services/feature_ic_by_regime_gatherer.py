"""Feature IC × Rejim'in girdisini GERÇEK kapanmış kararlardan toplayan
tek kaynak — Faz 364-devam. analytics/feature_ic_by_regime.py saf kalıyor,
gerçek veriye dokunan kod burada (feature_ic_gatherer/tasks.py'deki AYNI
100_000-limit deseni)."""
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.feature_ic_by_regime import compute_feature_ic_by_regime

MAX_DECISIONS = 100_000


def gather_feature_ic_by_regime() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=MAX_DECISIONS)

    by_regime = compute_feature_ic_by_regime(closed_trades)
    return {
        "by_regime": by_regime,
        "n_decisions_analyzed": len(closed_trades),
        "evaluation_window": describe_evaluation_window(closed_trades, limit=MAX_DECISIONS),
    }
