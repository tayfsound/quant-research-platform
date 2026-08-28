"""Feature Relationship'ın girdisini GERÇEK kapanmış kararlardan toplayan
tek kaynak — Faz 368. analytics/feature_relationship.py saf kalıyor,
gerçek veriye dokunan kod burada (feature_ic_by_regime_gatherer.py'deki
AYNI 100_000-limit deseni)."""
from analytics.feature_ic import compute_feature_ic
from analytics.feature_relationship import compute_conditional_ic, compute_feature_redundancy

MAX_DECISIONS = 100_000


def gather_feature_relationship() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=MAX_DECISIONS)

    feature_ic = compute_feature_ic(closed_trades)
    redundancy = compute_feature_redundancy(closed_trades)
    conditional_ic = compute_conditional_ic(closed_trades, redundancy, feature_ic)

    return {
        "redundancy": redundancy,
        "conditional_ic": conditional_ic,
        "n_decisions_analyzed": len(closed_trades),
    }
