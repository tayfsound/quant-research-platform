"""LLM Audit Run repository — Faz 271."""
from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.llm_audit_run import LLMAuditRun
from database.base import Base


class LLMAuditRunModel(Base):
    __tablename__ = "llm_audit_runs"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    response = Column(Text, nullable=False)
    tool_calls = Column(JSONB, nullable=False)
    proposals_created = Column(Integer, default=0)
    # Faz 282 — bkz. contracts/llm_audit_run.py::LLMAuditRun.status.
    status = Column(Text, nullable=False, server_default="ok")


class LLMAuditRunRepository:
    def __init__(self, session):
        self.session = session

    def save(self, run: LLMAuditRun) -> None:
        row = LLMAuditRunModel(
            id=run.id,
            created_at=run.created_at,
            response=run.response,
            tool_calls=run.tool_calls,
            proposals_created=run.proposals_created,
            status=run.status,
        )
        self.session.add(row)
        self.session.commit()

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(LLMAuditRunModel)
            .order_by(LLMAuditRunModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: LLMAuditRunModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "response": row.response,
            "tool_calls": row.tool_calls,
            "proposals_created": row.proposals_created,
            "status": row.status,
        }
