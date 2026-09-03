"""Agent Ablation'ın girdisini GERÇEK kapanmış kararlardan toplayan tek
kaynak — Faz 296. analytics/agent_ablation.py saf (pure) kalıyor, gerçek
veriye dokunan kod burada. pump_fade_v1 hariç (council oylaması yok,
mekanik strateji — ablation anlamsız)."""
from analytics.agent_ablation import compute_leave_one_out_impact, summarize_ablation_by_domain
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.measurement_stability import compute_stability
from contracts.agent import VOTING_AGENT_DOMAINS
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 3000
STABILITY_LOOKBACK_SNAPSHOTS = 12


def _attach_win_rate_stability(by_domain: dict[str, dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." SADECE gözlem."""
    past_by_domain: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for domain, stat in ((snap.get("result") or {}).get("by_domain") or {}).items():
            past_by_domain.setdefault(domain, []).append(stat.get("caused_trade_win_rate"))

    for domain, stat in by_domain.items():
        series = [*past_by_domain.get(domain, []), stat.get("caused_trade_win_rate")]
        stat["caused_trade_win_rate_stability"] = compute_stability(series)


def gather_agent_ablation() -> dict:
    from database.repositories.agent_ablation_report_repository import AgentAblationReportRepository
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
        past_snapshots = AgentAblationReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)

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
    _attach_win_rate_stability(by_domain, past_snapshots)
    return {
        "by_domain": by_domain,
        "n_decisions_analyzed": len(closed_trades),
        "evaluation_window": describe_evaluation_window(
            closed_trades, limit=MAX_DECISIONS, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
    }
