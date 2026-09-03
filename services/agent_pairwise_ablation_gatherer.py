"""Agent Interaction (pairwise ablation) girdisini GERÇEK kapanmış
kararlardan toplayan tek kaynak — Faz 368-devam. GPT'nin "A+B birlikte
yokken ne olur?" önerisi: agent_ablation_gatherer.py'nin tek-domain
leave-one-out'unun ötesine geçip, aynı kararda BİRLİKTE oy veren HER
ajan çiftini (VOTING_AGENT_DOMAINS'ten, C(12,2)=66 çift) karşı-olgusal
olarak yeniden sentezliyor. analytics/agent_ablation.py saf kalıyor,
gerçek veriye dokunan kod burada — agent_ablation_gatherer.py ile AYNI
MAX_DECISIONS/pump_fade dışlama deseni."""
from itertools import combinations

from analytics.agent_ablation import (
    classify_pairwise_relationship,
    compute_pairwise_ablation_interaction,
    reconstruct_opinions,
    summarize_pairwise_ablation_by_domain_pair,
)
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.measurement_stability import compute_stability
from contracts.agent import VOTING_AGENT_DOMAINS
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 3000
STABILITY_LOOKBACK_SNAPSHOTS = 12


def _attach_substitution_rate_stability(by_pair: dict[str, dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." SADECE gözlem — bir ajan
    çiftinin "birbirinin yerini tutma oranı"nın haftadan haftaya ne
    kadar tutarlı olduğunu ekliyor."""
    past_by_pair: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for pair, stat in ((snap.get("result") or {}).get("by_pair") or {}).items():
            past_by_pair.setdefault(pair, []).append(stat.get("substitution_rate"))

    for pair, stat in by_pair.items():
        series = [*past_by_pair.get(pair, []), stat.get("substitution_rate")]
        stat["substitution_rate_stability"] = compute_stability(series)


def gather_agent_pairwise_ablation() -> dict:
    from database.repositories.agent_pairwise_ablation_report_repository import (
        AgentPairwiseAblationReportRepository,
    )
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
        past_snapshots = AgentPairwiseAblationReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)

    domain_names = sorted(d.value for d in VOTING_AGENT_DOMAINS)
    records = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        actual_direction = t.get("direction")
        pnl = t.get("pnl")
        if not contributions or not actual_direction or pnl is None:
            continue

        # Her karar için opinions BİR KEZ rekonstrükte edilir — 66 çiftin
        # her biri için compute_pairwise_ablation_interaction'ı AYNI ham
        # veriden tekrar çağırmak yerine, o kararda GERÇEKTEN oy kullanan
        # domain'ler önceden filtrelenip sadece o alt-küme içindeki
        # çiftler denenir (pump_fade'de olduğu gibi çoğu karar 12
        # domain'in hepsinde değil bir alt-kümesinde oy alır).
        present_domains = {o.domain.value for o in reconstruct_opinions(contributions)} & set(domain_names)
        for domain_a, domain_b in combinations(sorted(present_domains), 2):
            interaction = compute_pairwise_ablation_interaction(
                contributions, domain_a, domain_b, actual_direction
            )
            if interaction is None:
                continue
            relationship = classify_pairwise_relationship(
                interaction["a_alone_impact"], interaction["b_alone_impact"], interaction["both_removed_impact"]
            )
            records.append({
                "pair": f"{domain_a}|{domain_b}",
                "relationship": relationship,
                "both_removed_pnl": float(pnl) if interaction["both_removed_impact"] == "caused_trade" else 0.0,
            })

    by_pair = summarize_pairwise_ablation_by_domain_pair(records)
    _attach_substitution_rate_stability(by_pair, past_snapshots)
    return {
        "by_pair": by_pair,
        "n_decisions_analyzed": len(closed_trades),
        "evaluation_window": describe_evaluation_window(
            closed_trades, limit=MAX_DECISIONS, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
    }
