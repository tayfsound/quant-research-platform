"""Direction Analog'un (Faz 445) girdisini GERÇEK kapanmış kararlardan +
gerçek piyasa fiyatından toplayan tek kaynak — analytics/historical_
analog_engine.py::compute_direction_analogs() saf (pure) kalıyor, gerçek
veriye dokunan kod burada. services/historical_analog_gatherer.py'nin
AYNI agreeing_domains/market_regime/reversing çıkarma mantığı + services/
direction_baseline_gatherer.py'nin AYNI LATERAL JOIN'i (sabit ufuklu
ileri fiyat) — ikisi birlikte forward_label üretiyor."""
from datetime import timedelta

from analytics.agent_combination_reliability import agreeing_domains_for_decision
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.forward_direction import DEFAULT_THRESHOLD_PCT, label_forward_direction
from analytics.historical_analog_engine import compute_direction_analogs
from market_data.features.market_state_engine import market_state_reversing_for_decision
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 2000
DEFAULT_HORIZON = timedelta(hours=1)
DEFAULT_TOLERANCE_MINUTES = 5.0


def gather_direction_analogs(
    horizon: timedelta = DEFAULT_HORIZON,
    tolerance_minutes: float = DEFAULT_TOLERANCE_MINUTES,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    tolerance = timedelta(minutes=tolerance_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("""
                SELECT d.agent_contributions, d.market_regime, d.direction, d.closed_at,
                       d.entry_price, ms.close AS price_at_horizon
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
                  AND d.entry_price IS NOT NULL AND d.entry_price != 0
                  AND (d.experiment_bucket IS NULL OR d.experiment_bucket != :exclude_bucket)
                ORDER BY d.timestamp DESC
                LIMIT :limit
            """),
            {
                "horizon": horizon, "tolerance": tolerance,
                "exclude_bucket": PUMP_FADE_EXPERIMENT_BUCKET, "limit": MAX_DECISIONS,
            },
        ).mappings().all()

    records = []
    for r in rows:
        contributions = r["agent_contributions"]
        final_direction = r["direction"]
        market_regime = r["market_regime"]
        if not contributions or not final_direction or not market_regime:
            continue
        agreeing = agreeing_domains_for_decision(contributions, final_direction)
        if agreeing is None:
            continue
        forward_label = label_forward_direction(r["entry_price"], r["price_at_horizon"], threshold_pct)
        records.append({
            "agreeing_domains": agreeing,
            "market_regime": market_regime,
            "direction": final_direction,
            "reversing": market_state_reversing_for_decision(contributions),
            "forward_label": forward_label,
            "closed_at": r["closed_at"],
        })

    result = compute_direction_analogs(records)
    result["n_trades"] = len(records)
    result["evaluation_window"] = describe_evaluation_window(
        [dict(r) for r in rows], limit=MAX_DECISIONS,
        exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
    )
    return result
