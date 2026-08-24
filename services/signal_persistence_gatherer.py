"""Faz 362 — signal_persistence'ın girdisini GERÇEK kapanmış işlemlerden
toplayan tek kaynak. analytics/signal_persistence.py saf kalıyor — gerçek
veriye dokunan kod burada, mae_mfe_confidence_gatherer.py/scientific_
self_correction_gatherer.py ile AYNI desen.

Her çağrıda TAZE hesaplanıyor (hiçbir şey önceden saklanmıyor) — kullanıcı
isteği: "data büyüdükçe optimum N değişebilir, sürekli ölçülsün." Canlı
gate'lerin KENDİLERİ (services/decision_recorder.py, services/belief_
reversal_exit.py) bu modülü ÇAĞIRMIYOR — otomatik "en iyi N'i her
cycle'da canlıya uygula" YAPMIYORUZ (gürültülü/küçük örneklemli bir günde
ayarın sessizce sıçraması riski) — sadece GÖZLEM/ÖNERİ katmanı. Ayarları
(signal_persistence_min_consistent_cycles, belief_reversal_exit_min_
consistent_cycles) değiştirmek her zaman kullanıcının bilinçli kararı.

Faz 362-devam — kullanıcı isteği: "aynı sayfada görüntüleyebiliriz, aynı
kısım aslında" — GİRİŞ (sinyal tutarlılığı) ve ÇIKIŞ (inanç tersine
dönüşü) analizleri AYNI gather fonksiyonunun döndürdüğü tek payload'da,
iki ayrı anahtar altında birleştirildi — ikisi de "council'in sinyali
şu an ne kadar güvenilir" sorusunun iki yüzü."""
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from analytics.signal_persistence import (
    consecutive_reversal_run_length,
    consistent_direction_run_length,
    find_optimal_persistence_threshold,
    find_optimal_reversal_exit_threshold,
)
from database.session_factory import SessionFactory

DEFAULT_WINDOW_DAYS = 14
_MECHANICAL_EXPERIMENT_BUCKETS = ("pump_fade_v1", "basis_arb_v1")
_REVERSAL_CONFIDENCE_THRESHOLD = 0.65
_REVERSAL_MAX_N = 12


def _fetch_positions_and_decisions(window_days: int, need_entry_fields: bool):
    since = datetime.now(UTC) - timedelta(days=window_days)
    fields = "id, symbol, direction, pnl, opened_at"
    if need_entry_fields:
        fields += ", entry_price, quantity, closed_at"

    with SessionFactory.get_session() as session:
        positions = session.execute(text(f"""
            SELECT {fields}
            FROM decisions
            WHERE status='closed' AND opened_at >= :since
              AND (experiment_bucket IS NULL OR experiment_bucket NOT IN :mechanical)
              {"AND entry_price IS NOT NULL AND quantity IS NOT NULL" if need_entry_fields else ""}
        """), {"since": since, "mechanical": _MECHANICAL_EXPERIMENT_BUCKETS}).mappings().all()
        positions = [dict(r) for r in positions]
        if not positions:
            return [], defaultdict(list)

        symbols = {p["symbol"] for p in positions}
        decisions = session.execute(text("""
            SELECT id, symbol, direction, confidence, timestamp
            FROM decisions
            WHERE symbol = ANY(:symbols) AND timestamp >= :since
            ORDER BY symbol, timestamp ASC
        """), {"symbols": list(symbols), "since": since}).mappings().all()

    by_symbol = defaultdict(list)
    for d in decisions:
        by_symbol[d["symbol"]].append(d)
    return positions, by_symbol


def _gather_entry_persistence(window_days: int) -> dict:
    positions, by_symbol = _fetch_positions_and_decisions(window_days, need_entry_fields=False)
    if not positions:
        return {"sample_count": 0, "optimal_n": None, "table": []}

    run_length_and_pnl: list[tuple[int, float]] = []
    for pos in positions:
        prior_asc = [d for d in by_symbol[pos["symbol"]] if d["timestamp"] < pos["opened_at"]]
        prior_desc = [{"direction": d["direction"]} for d in reversed(prior_asc)]
        run = consistent_direction_run_length(prior_desc, pos["direction"])
        run_length_and_pnl.append((run, pos["pnl"] or 0.0))

    result = find_optimal_persistence_threshold(run_length_and_pnl)
    return {"sample_count": len(positions), "optimal_n": result["optimal_n"], "table": result["table"]}


def _gather_exit_reversal(window_days: int) -> dict:
    positions, by_symbol = _fetch_positions_and_decisions(window_days, need_entry_fields=True)
    if not positions:
        return {"sample_count": 0, "optimal_n": None, "table": []}

    # her pozisyon icin, N=1..max her run-uzunlugunda ILK tetikleyici
    # kararin id'sini buluyoruz (belief_reversal_exit.py'nin canli
    # mantigiyla AYNI run-length hesabi, sadece pencere ici tum gecmis
    # taranarak).
    confirm_id_by_n: dict[int, dict[str, str]] = {n: {} for n in range(1, _REVERSAL_MAX_N + 1)}
    for pos in positions:
        candidates = [
            d for d in by_symbol[pos["symbol"]]
            if pos["opened_at"] < d["timestamp"] < pos["closed_at"]
        ]
        opposite = "SHORT" if pos["direction"] == "LONG" else "LONG"
        run = 0
        last_id_at_run_length: dict[int, str] = {}
        for d in candidates:
            if d["direction"] == opposite and (d["confidence"] or 0) >= _REVERSAL_CONFIDENCE_THRESHOLD:
                run += 1
                if run <= _REVERSAL_MAX_N and run not in last_id_at_run_length:
                    last_id_at_run_length[run] = str(d["id"])
            else:
                run = 0
        for n, dec_id in last_id_at_run_length.items():
            confirm_id_by_n[n][str(pos["id"])] = dec_id

    needed_ids = {dec_id for m in confirm_id_by_n.values() for dec_id in m.values()}
    price_by_id: dict[str, float] = {}
    if needed_ids:
        needed_ids_list = list(needed_ids)
        chunk = 1000
        with SessionFactory.get_session() as session:
            for i in range(0, len(needed_ids_list), chunk):
                batch = needed_ids_list[i:i + chunk]
                ac_rows = session.execute(text("""
                    SELECT id, agent_contributions FROM decisions WHERE id::text = ANY(:ids)
                """), {"ids": batch}).mappings().all()
                for r in ac_rows:
                    for item in (r["agent_contributions"] or []):
                        if isinstance(item, dict) and item.get("type") == "market_snapshot":
                            raw = item.get("data") or {}
                            close = (raw.get("raw_snapshot") or {}).get("close")
                            if close is not None:
                                price_by_id[str(r["id"])] = close
                            break

    pos_by_id = {str(p["id"]): p for p in positions}
    diffs_by_n: dict[int, list[float]] = {}
    for n, matched in confirm_id_by_n.items():
        diffs = []
        for pos_id, dec_id in matched.items():
            price = price_by_id.get(dec_id)
            if price is None:
                continue
            pos = pos_by_id[pos_id]
            entry = pos["entry_price"]
            qty = pos["quantity"]
            if pos["direction"] == "LONG":
                pnl_if_exited = (price - entry) * qty
            else:
                pnl_if_exited = (entry - price) * qty
            diffs.append(pnl_if_exited - (pos["pnl"] or 0.0))
        if diffs:
            diffs_by_n[n] = diffs

    result = find_optimal_reversal_exit_threshold(diffs_by_n)
    return {
        "sample_count": len(positions),
        "confidence_threshold": _REVERSAL_CONFIDENCE_THRESHOLD,
        "optimal_n": result["optimal_n"],
        "table": result["table"],
    }


def gather_signal_persistence_analysis(window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
    return {
        "window_days": window_days,
        "entry_persistence": _gather_entry_persistence(window_days),
        "exit_reversal": _gather_exit_reversal(window_days),
    }
