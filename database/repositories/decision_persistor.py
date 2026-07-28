"""Decision persistence — Phase 170."""

from sqlalchemy import text
from contracts.decision_event import DecisionEvent


class DecisionPersistor:
    def __init__(self, session):
        self.session = session

    def persist(self, event: DecisionEvent) -> None:
        self.session.execute(
            text("""
                INSERT INTO decisions (
                    id, timestamp, symbol, direction, size, confidence,
                    agent_contributions, weight_snapshot_id, belief_snapshot_id, status
                )
                VALUES (
                    :id, :timestamp, :symbol, :direction, :size, :confidence,
                    :agent_contributions, :weight_snapshot_id, :belief_snapshot_id, :status
                )
            """),
            {
                "id": str(event.id),
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "direction": event.direction,
                "size": event.size,
                "confidence": event.confidence,
                "agent_contributions": event.agent_contributions,
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
            {"id": decision_id, "pnl": pnl, "status": status},
        )
        self.session.commit()
