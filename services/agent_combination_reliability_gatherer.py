"""Agent Combination Reliability'nin girdisini GERÇEK kapanmış kararlardan
toplayan tek kaynak — Faz 331. analytics/agent_combination_reliability.py
saf (pure) kalıyor, gerçek veriye dokunan kod burada. pump_fade_v1 hariç
(council oylaması yok, mekanik strateji — anlaşma kavramı anlamsız) —
Opportunity Quality/Agent Ablation ile AYNI dışlama."""
from analytics.agent_combination_reliability import (
    agreeing_domains_for_decision,
    compute_combination_reliability,
)
from analytics.evaluation_cohort import describe_evaluation_window
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 2000


def gather_agent_combination_reliability() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    records = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        final_direction = t.get("direction")
        pnl = t.get("pnl")
        if not contributions or not final_direction or pnl is None:
            continue
        agreeing = agreeing_domains_for_decision(contributions, final_direction)
        if agreeing is None:
            continue
        records.append({"agreeing_domains": agreeing, "win": pnl > 0, "closed_at": t.get("closed_at")})

    result = compute_combination_reliability(records)
    result["n_trades"] = len(records)
    # Faz 400 — canonical evaluation cohort görünürlüğü: n_trades ANALİZDE
    # KULLANILAN alt kümeyi (usable contributions/direction/pnl), evaluation_
    # window ise SORGULANAN ham pencereyi anlatıyor — ikisi kasıtlı olarak farklı.
    result["evaluation_window"] = describe_evaluation_window(
        closed_trades, limit=MAX_DECISIONS, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
    )
    return result
