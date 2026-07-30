"""Decision persistence — Phase 170."""

import json

from sqlalchemy import text

from contracts.decision_event import DecisionEvent


class DecisionPersistor:
    def __init__(self, session):
        self.session = session

    def persist(self, event: DecisionEvent) -> None:
        agent_contributions = list(event.agent_opinions) if event.agent_opinions else []

        if event.risk_evaluation:
            agent_contributions.append({
                "type": "risk_evaluation",
                "data": event.risk_evaluation
            })

        self.session.execute(
            text("""
                INSERT INTO decisions (
                    id, timestamp, symbol, direction, size, confidence,
                    agent_contributions, weight_snapshot_id, belief_snapshot_id, status
                )
                VALUES (
                    :id, :timestamp, :symbol, :direction, :size, :confidence,
                    CAST(:agent_contributions AS jsonb), :weight_snapshot_id, :belief_snapshot_id, :status
                )
            """),
            {
                "id": str(event.id),
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "direction": event.proposed_direction or event.final_action or "WAIT",
                "size": event.final_size,
                "confidence": event.confidence,
                "agent_contributions": json.dumps(
                    agent_contributions,
                    default=str
                ),
                "weight_snapshot_id": str(event.weight_snapshot_id) if event.weight_snapshot_id else None,
                "belief_snapshot_id": str(event.belief_snapshot_id) if event.belief_snapshot_id else None,
                "status": "pending",
            },
        )

        self.session.commit()

    def get_by_symbol(self, symbol: str, limit: int = 100) -> list[dict]:
        result = self.session.execute(
            text("SELECT * FROM decisions WHERE symbol = :symbol ORDER BY timestamp DESC LIMIT :limit"),
            {"symbol": symbol, "limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]

    def update_outcome(self, decision_id: str, pnl: float, status: str) -> None:
        self.session.execute(
            text("UPDATE decisions SET pnl = :pnl, status = :status WHERE id = :id"),
            {
                "id": decision_id,
                "pnl": pnl,
                "status": status
            },
        )
        self.session.commit()
