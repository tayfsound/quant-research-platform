"""Strategy × Regime Compatibility'nin girdisini GERÇEK kapanmış
kararlardan toplayan tek kaynak — Faz 338 (MetaStrategyAgent v1).
analytics/strategy_regime_compatibility.py saf (pure) kalıyor, gerçek
veriye dokunan kod burada.

"strategy" etiketi: pump_fade_v1 experiment_bucket'ı "pump_fade", geri
kalan HER ŞEY (AI council + dormant multi_timeframe_cascade_v1 A/B
deneyi dahil) "ai_council" — v1'de kasıtlı olarak kaba/basit, tek
gerçek mekanik/izole strateji (pump_fade) ile council'in geri kalanını
ayırt etmek yeterli."""
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 5000


def _strategy_label(experiment_bucket: str | None) -> str:
    return "pump_fade" if experiment_bucket == PUMP_FADE_EXPERIMENT_BUCKET else "ai_council"


def gather_strategy_regime_compatibility() -> dict:
    from database.session_factory import SessionFactory
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT experiment_bucket, market_regime, pnl
                FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND market_regime IS NOT NULL
                ORDER BY closed_at DESC
                LIMIT :limit
                """
            ),
            {"limit": MAX_DECISIONS},
        ).fetchall()

    records = [
        {
            "strategy": _strategy_label(r.experiment_bucket),
            "market_regime": r.market_regime,
            "win": (r.pnl or 0.0) > 0,
        }
        for r in rows
    ]

    from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility

    result = compute_strategy_regime_compatibility(records)
    return {"by_strategy": result, "n_decisions_analyzed": len(records)}
