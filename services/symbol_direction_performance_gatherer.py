"""Symbol×Direction Performance — Faz 368, kullanıcı bulgusu (Grok raporu
doğrulaması): council SL zararları belirli sembol×yön hücrelerinde
sistematik olarak yoğunlaşıyor (ör. ATOMUSDT_LONG≈-38k, ALGOUSDT_LONG≈
-14k, AVAXUSDT_LONG≈-13.6k) — genel/ajan-bazlı ölçümlerin hiçbiri bunu
yakalamıyordu. analytics/symbol_performance_sizing_gate.py saf kalıyor,
gerçek veriye dokunan kod burada — services/pump_fade_strategy.py'nin
EXPERIMENT_BUCKET'ıyla AYNI dışlama (mekanik stratejiler council'in
sembol-bazlı becerisini yansıtmıyor, agent_combination_reliability_
gatherer.py ile AYNI ilke)."""
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

_BASIS_ARB_EXPERIMENT_BUCKET = "basis_arb_v1"


def gather_symbol_direction_performance() -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT symbol, direction, COUNT(*) n, "
                "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) wins, SUM(pnl) total_pnl "
                "FROM decisions "
                "WHERE status = 'closed' AND excluded_from_stats = false "
                "AND direction IN ('LONG', 'SHORT') "
                "AND (experiment_bucket IS NULL OR experiment_bucket NOT IN (:pump_fade, :basis_arb)) "
                "GROUP BY symbol, direction"
            ),
            {"pump_fade": PUMP_FADE_EXPERIMENT_BUCKET, "basis_arb": _BASIS_ARB_EXPERIMENT_BUCKET},
        ).mappings().all()

    by_symbol_direction = {}
    for row in rows:
        n = row["n"]
        by_symbol_direction[f"{row['symbol']}_{row['direction']}"] = {
            "sample_size": n,
            "win_rate": round(row["wins"] / n, 4) if n else None,
            "total_pnl": round(float(row["total_pnl"]), 2) if row["total_pnl"] is not None else 0.0,
        }
    return {"by_symbol_direction": by_symbol_direction}
