"""Sprint 16: assembles the full explainability chain for one decision —
"Neden BUY? -> hangi agent? -> hangi evidence? -> hangi belief? -> hangi
debate? -> hangi risk? -> hangi weight? -> hangi outcome?" Every piece
already exists (DecisionEvent fields, belief_snapshots, weight_history);
this just resolves the foreign keys and joins them into one response, using
real stored data — not a mock happy path.
"""


class ExplainabilityService:
    def __init__(self, decision_repo, belief_repo, weight_repo):
        self.decision_repo = decision_repo
        self.belief_repo = belief_repo
        self.weight_repo = weight_repo

    def explain(self, decision_id: str) -> dict | None:
        decision = self.decision_repo.get_by_id(decision_id)
        if not decision:
            return None

        contributions = decision.get("agent_contributions") or []
        agent_opinions = [
            c for c in contributions
            if isinstance(c, dict) and "type" not in c and "_type" not in c
        ]
        risk_evaluation = next(
            (c["data"] for c in contributions if isinstance(c, dict) and c.get("type") == "risk_evaluation"),
            None,
        )
        market_snapshot = next(
            (c["data"] for c in contributions if isinstance(c, dict) and c.get("type") == "market_snapshot"),
            None,
        )
        debate_result = next(
            (c["data"] for c in contributions if isinstance(c, dict) and c.get("_type") == "debate_result"),
            None,
        )

        belief = None
        belief_snapshot_id = decision.get("belief_snapshot_id")
        if belief_snapshot_id:
            belief = self.belief_repo.get_by_id(belief_snapshot_id)

        weight_snapshot = None
        weight_snapshot_id = decision.get("weight_snapshot_id")
        if weight_snapshot_id:
            snap = self.weight_repo.get_by_id(weight_snapshot_id)
            weight_snapshot = snap.model_dump(mode="json") if snap else None

        return {
            "decision_id": str(decision["id"]),
            "symbol": decision.get("symbol"),
            "direction": decision.get("direction"),
            "size": decision.get("size"),
            "confidence": decision.get("confidence"),
            "chain": {
                "agents": agent_opinions,
                "evidence": market_snapshot,
                "belief": belief,
                "debate": debate_result,
                "risk": risk_evaluation,
                "weight_snapshot": weight_snapshot,
                "outcome": decision.get("outcome"),
            },
        }
