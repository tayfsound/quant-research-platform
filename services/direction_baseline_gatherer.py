"""Direction Baseline Karşılaştırmasının girdisini GERÇEK kapanmış
kararlardan + gerçek piyasa fiyatından toplayan tek kaynak — Faz 442
(2026-09-07, Direction Prediction Engine). analytics/direction_
baseline_comparison.py saf (pure) kalıyor, gerçek veriye dokunan kod
burada.

Bugünkü LATERAL JOIN prototipinin (bir karar zamanına en yakın 'N saat
sonraki' gerçek fiyatı bulmak) resmi hâli — `market_data_repository.py::
get_price_at_horizon()`'ı TEK TEK (binlerce karar için) çağırmak yerine
AYNI mantığı tek bir toplu SQL sorgusunda çalıştırıyor (performans),
ama SONUCU aynı `analytics/forward_direction.py::label_forward_
direction()`'a besliyor — iki yol da AYNI fonksiyona ulaşıyor."""
from datetime import timedelta

MAX_DECISIONS = 8000
DEFAULT_HORIZON = timedelta(hours=1)
DEFAULT_TOLERANCE_MINUTES = 5.0
DEFAULT_LOOKBACK_DAYS = 10


def gather_direction_baseline_comparison(
    horizon: timedelta = DEFAULT_HORIZON,
    tolerance_minutes: float = DEFAULT_TOLERANCE_MINUTES,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict:
    from sqlalchemy import text

    from analytics.direction_baseline_comparison import compute_baseline_comparison
    from analytics.evaluation_cohort import describe_evaluation_window
    from database.session_factory import SessionFactory

    tolerance = timedelta(minutes=tolerance_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("""
                SELECT d.symbol, d.direction, d.council_direction, d.market_regime,
                       d.entry_price, d.timestamp, d.closed_at,
                       ms.close AS price_at_horizon
                FROM decisions d
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :horizon - :tolerance
                                        AND d.timestamp + :horizon + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :horizon))))
                    LIMIT 1
                ) ms ON true
                WHERE d.status = 'closed' AND d.excluded_from_stats = false
                  AND d.direction IN ('LONG', 'SHORT')
                  AND d.entry_price IS NOT NULL AND d.entry_price != 0
                  AND (d.experiment_bucket IS NULL OR d.experiment_bucket NOT IN ('pump_fade_v1', 'basis_arb_v1'))
                  AND d.timestamp >= now() - :lookback
                ORDER BY d.timestamp DESC
                LIMIT :limit
            """),
            {
                "horizon": horizon, "tolerance": tolerance,
                "lookback": timedelta(days=lookback_days), "limit": MAX_DECISIONS,
            },
        ).mappings().all()

    records = [
        {
            "entry_price": r["entry_price"], "price_at_horizon": r["price_at_horizon"],
            "direction": r["direction"], "council_direction": r["council_direction"],
            "market_regime": r["market_regime"],
        }
        for r in rows
    ]
    result = compute_baseline_comparison(records)
    return {
        "horizon_minutes": round(horizon.total_seconds() / 60, 1),
        "comparison": result,
        "evaluation_window": describe_evaluation_window(
            [dict(r) for r in rows], limit=MAX_DECISIONS,
            exclude_experiment_buckets=["pump_fade_v1", "basis_arb_v1"],
        ),
    }
