"""Çoklu Ufuk Uyuşmazlığı raporunun girdisini GERÇEK kapanmış kararlardan
+ gerçek piyasa fiyatından toplayan tek kaynak — Faz 444 (2026-09-07,
Direction Prediction Engine). analytics/multi_horizon_direction.py saf
(pure) kalıyor, gerçek veriye dokunan kod burada.

services/direction_baseline_gatherer.py'nin AYNI LATERAL JOIN deseni,
tek farkı: bir ufuk yerine ÜÇ ufku (15m/1h/4h) TEK sorguda, üç ayrı
LATERAL JOIN ile birlikte çekiyor (üç ayrı sorgu yerine)."""
from datetime import timedelta

MAX_DECISIONS = 8000
DEFAULT_TOLERANCE_MINUTES = 5.0
DEFAULT_LOOKBACK_DAYS = 10

_HORIZON_DELTAS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
}


def gather_multi_horizon_disagreement(
    tolerance_minutes: float = DEFAULT_TOLERANCE_MINUTES,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict | None:
    from sqlalchemy import text

    from analytics.multi_horizon_direction import compute_disagreement_rate
    from database.session_factory import SessionFactory

    tolerance = timedelta(minutes=tolerance_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("""
                SELECT d.symbol, d.entry_price,
                       ms15.close AS price_15m, ms1h.close AS price_1h, ms4h.close AS price_4h
                FROM decisions d
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :h15 - :tolerance AND d.timestamp + :h15 + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :h15))))
                    LIMIT 1
                ) ms15 ON true
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :h1h - :tolerance AND d.timestamp + :h1h + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :h1h))))
                    LIMIT 1
                ) ms1h ON true
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :h4h - :tolerance AND d.timestamp + :h4h + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :h4h))))
                    LIMIT 1
                ) ms4h ON true
                WHERE d.status = 'closed' AND d.excluded_from_stats = false
                  AND d.direction IN ('LONG', 'SHORT')
                  AND d.entry_price IS NOT NULL AND d.entry_price != 0
                  AND (d.experiment_bucket IS NULL OR d.experiment_bucket NOT IN ('pump_fade_v1', 'basis_arb_v1'))
                  AND d.timestamp >= now() - :lookback AND d.timestamp <= now() - :h4h
                ORDER BY d.timestamp DESC
                LIMIT :limit
            """),
            {
                "h15": _HORIZON_DELTAS["15m"], "h1h": _HORIZON_DELTAS["1h"], "h4h": _HORIZON_DELTAS["4h"],
                "tolerance": tolerance, "lookback": timedelta(days=lookback_days), "limit": MAX_DECISIONS,
            },
        ).mappings().all()

    records = [
        {
            "symbol": r["symbol"], "entry_price": r["entry_price"],
            "price_15m": r["price_15m"], "price_1h": r["price_1h"], "price_4h": r["price_4h"],
        }
        for r in rows
    ]
    return compute_disagreement_rate(records)
