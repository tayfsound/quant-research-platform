"""Faz 362 — signal_persistence'ın girdisini GERÇEK kapanmış işlemlerden
toplayan tek kaynak. analytics/signal_persistence.py saf kalıyor — gerçek
veriye dokunan kod burada, mae_mfe_confidence_gatherer.py/scientific_
self_correction_gatherer.py ile AYNI desen.

Her çağrıda TAZE hesaplanıyor (hiçbir şey önceden saklanmıyor) — kullanıcı
isteği: "data büyüdükçe optimum N değişebilir, sürekli ölçülsün." Canlı
gate'in KENDİSİ (services/decision_recorder.py) bu modülü ÇAĞIRMIYOR —
otomatik "en iyi N'i her cycle'da canlıya uygula" YAPMIYORUZ (gürültülü/
küçük örneklemli bir günde ayarın sessizce sıçraması riski) — sadece
GÖZLEM/ÖNERİ katmanı. Ayarı (`signal_persistence_min_consistent_cycles`)
değiştirmek her zaman kullanıcının bilinçli kararı."""
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from analytics.signal_persistence import consistent_direction_run_length, find_optimal_persistence_threshold
from database.session_factory import SessionFactory

DEFAULT_WINDOW_DAYS = 14
_MECHANICAL_EXPERIMENT_BUCKETS = ("pump_fade_v1", "basis_arb_v1")


def gather_signal_persistence_analysis(window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
    since = datetime.now(UTC) - timedelta(days=window_days)

    with SessionFactory.get_session() as session:
        positions = session.execute(text("""
            SELECT id, symbol, direction, pnl, opened_at
            FROM decisions
            WHERE status='closed' AND opened_at >= :since
              AND (experiment_bucket IS NULL OR experiment_bucket NOT IN :mechanical)
        """), {"since": since, "mechanical": _MECHANICAL_EXPERIMENT_BUCKETS}).mappings().all()
        positions = [dict(r) for r in positions]
        if not positions:
            return {"window_days": window_days, "sample_count": 0, "optimal_n": None, "table": []}

        symbols = {p["symbol"] for p in positions}
        decisions = session.execute(text("""
            SELECT symbol, direction, timestamp
            FROM decisions
            WHERE symbol = ANY(:symbols) AND timestamp >= :since
            ORDER BY symbol, timestamp ASC
        """), {"symbols": list(symbols), "since": since}).mappings().all()

    by_symbol = defaultdict(list)
    for d in decisions:
        by_symbol[d["symbol"]].append(d)

    run_length_and_pnl: list[tuple[int, float]] = []
    for pos in positions:
        prior_asc = [d for d in by_symbol[pos["symbol"]] if d["timestamp"] < pos["opened_at"]]
        prior_desc = [{"direction": d["direction"]} for d in reversed(prior_asc)]
        run = consistent_direction_run_length(prior_desc, pos["direction"])
        run_length_and_pnl.append((run, pos["pnl"] or 0.0))

    result = find_optimal_persistence_threshold(run_length_and_pnl)
    return {
        "window_days": window_days,
        "sample_count": len(positions),
        "optimal_n": result["optimal_n"],
        "table": result["table"],
    }
