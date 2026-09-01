"""Rejim Performansı'nın girdisini GERÇEK kapanmış AI konseyi
kararlarından toplayan tek kaynak. analytics/regime_performance.py saf
kalıyor. pump_fade_v1/basis_arb_v1 hariç — bu kart SADECE AI konseyinin
rejim-bazlı başarısını gösteriyor, regime_trading_gate'in kapsamıyla
AYNI (mekanik stratejiler kendi rejim kavramını kullanmıyor).

Faz 367-devam — kullanıcı bulgusu (2026-08-27, bkz. asset_class_
performance_gatherer.py'nin AYNI notu): multi_timeframe_cascade_v1
(A/B deneyi) da ayrı tutuluyor — üretim AI performansı, deney sonucu
değil."""
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.regime_performance import compute_regime_performance
from services.asset_class_performance_gatherer import _is_production_ai_council
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 5000


def gather_regime_performance() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
    closed_trades = [t for t in closed_trades if _is_production_ai_council(t.get("experiment_bucket"))]

    by_regime = compute_regime_performance(closed_trades)
    return {
        "by_regime": by_regime,
        "n_trades_analyzed": len(closed_trades),
        "evaluation_window": describe_evaluation_window(
            closed_trades, limit=MAX_DECISIONS, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
            production_ai_council_filtered=True,
        ),
    }
