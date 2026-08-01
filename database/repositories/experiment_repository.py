from __future__ import annotations

"""Experiment repository — commit yok."""
import json

from sqlalchemy import text

from contracts.curiosity import ExperimentProposal, ExperimentStatus


class ExperimentRepository:
    def __init__(self, session):
        self.session = session

    def save(self, proposal: ExperimentProposal):
        data = {
            "id": str(proposal.id),
            "curiosity_id": str(proposal.curiosity_id) if proposal.curiosity_id else None,
            "hypothesis": proposal.hypothesis,
            "test_expression": proposal.test_expression,
            "estimated_value": proposal.estimated_value,
            "status": proposal.status.value if hasattr(proposal.status, 'value') else str(proposal.status),
        }
        self.session.execute(
            text("""INSERT INTO experiments (id, curiosity_id, hypothesis, test_expression, estimated_value, status)
               VALUES (:id, :curiosity_id, :hypothesis, :test_expression, :estimated_value, :status)"""),
            data,
        )

    def update_status(self, experiment_id: str, status: ExperimentStatus, result: dict | None = None):
        self.session.execute(
            text("UPDATE experiments SET status = :status, result = :result WHERE id = :id"),
            {"id": experiment_id, "status": status.value, "result": json.dumps(result) if result else None},
        )

    def latest(self, limit: int = 20) -> list[dict]:
        result = self.session.execute(
            text("SELECT * FROM experiments ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]
