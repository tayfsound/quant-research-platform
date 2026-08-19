"""Opportunity Quality / Meta-Labeling'in girdisini GERÇEK kapanmış
işlemlerden toplayan tek kaynak — Cognitive Core 2.0 (Faz 569-593).
analytics/opportunity_quality.py::compute_agent_agreement()/
compute_opportunity_quality_by_agreement() saf (pure) kalıyor — gerçek
veriye dokunan kod burada.

Her kapanmış işlemin decisions.agent_contributions'ındaki GERÇEK ajan
oylarından (api/rest/positions.py::explain_position ile AYNI çıkarım
deseni) LONG/SHORT/WAIT sayımı yapılır, compute_agent_agreement ile
0-1 arası bir anlaşma skoruna çevrilir — pump_fade_v1 hariç (mekanik
strateji, council oylaması hiç yok)."""
from analytics.opportunity_quality import (
    compute_agent_agreement,
    compute_opportunity_quality_by_agreement,
)
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET


def _agreement_for_decision(row: dict) -> float | None:
    contributions = row.get("agent_contributions") or []
    votes = {"LONG": 0, "SHORT": 0, "WAIT": 0}
    found_any = False
    for item in contributions:
        if not isinstance(item, dict) or "domain" not in item:
            continue
        direction = (item.get("direction") or "").upper()
        if direction in votes:
            votes[direction] += 1
            found_any = True
    if not found_any:
        return None
    return compute_agent_agreement(votes)


def gather_opportunity_quality() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=2000, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    trades = []
    for t in closed_trades:
        agreement = _agreement_for_decision(t)
        pnl = t.get("pnl")
        if agreement is None or pnl is None:
            continue
        trades.append({"agent_agreement": agreement, "win": pnl > 0})

    by_agreement = compute_opportunity_quality_by_agreement(trades)
    return {"by_agreement_bucket": by_agreement, "n_trades": len(trades)}
