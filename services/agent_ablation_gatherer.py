"""Agent Ablation'ın girdisini GERÇEK kapanmış kararlardan toplayan tek
kaynak — Faz 296. analytics/agent_ablation.py saf (pure) kalıyor, gerçek
veriye dokunan kod burada. pump_fade_v1 hariç (council oylaması yok,
mekanik strateji — ablation anlamsız)."""
from analytics.agent_ablation import compute_leave_one_out_impact, summarize_ablation_by_domain
from contracts.agent import VOTING_AGENT_DOMAINS
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 3000


def gather_agent_ablation() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    records = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        actual_direction = t.get("direction")
        pnl = t.get("pnl")
        if not contributions or not actual_direction or pnl is None:
            continue
        for domain in VOTING_AGENT_DOMAINS:
            impact = compute_leave_one_out_impact(contributions, domain.value, actual_direction)
            if impact is not None:
                records.append({"domain": domain.value, "impact": impact, "pnl": float(pnl)})

    by_domain = summarize_ablation_by_domain(records)
    return {"by_domain": by_domain, "n_decisions_analyzed": len(closed_trades)}
