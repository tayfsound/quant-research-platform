"""Autonomous Strategy Synthesizer v1'in girdisini GERÇEK kapanmış
kararlardan toplayan tek kaynak — Faz 346. analytics/
strategy_hypothesis_scanner.py saf (pure) kalıyor, gerçek veriye
dokunan kod burada. strategy_regime_compatibility_gatherer.py ile AYNI
sorgu/etiketleme (strategy_regime_compatibility_gatherer.py::
_strategy_label) — tek fark: closed_at de çekiliyor (zaman sıralı
OOS bölünmesi için)."""
from services.strategy_regime_compatibility_gatherer import MAX_DECISIONS, _strategy_label


def gather_strategy_hypothesis_candidates() -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT experiment_bucket, market_regime, direction, pnl, entry_price, stop_loss_price, closed_at
                FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND market_regime IS NOT NULL
                ORDER BY closed_at ASC
                LIMIT :limit
                """
            ),
            {"limit": MAX_DECISIONS},
        ).fetchall()

    records = [
        {
            "strategy": _strategy_label(r.experiment_bucket, r.direction, r.entry_price, r.stop_loss_price),
            "market_regime": r.market_regime,
            "win": (r.pnl or 0.0) > 0,
        }
        for r in rows
    ]

    from analytics.strategy_hypothesis_scanner import (
        scan_for_gate_candidates,
        validate_candidate_out_of_sample,
    )

    candidates = scan_for_gate_candidates(records)
    for candidate in candidates:
        oos = validate_candidate_out_of_sample(records, candidate)
        candidate["out_of_sample"] = oos

    return {
        "candidates": candidates,
        "n_decisions_analyzed": len(records),
    }
