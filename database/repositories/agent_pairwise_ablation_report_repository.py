"""Agent Pairwise Ablation Report repository — Faz 368-devam."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.agent_pairwise_ablation_report import AgentPairwiseAblationReport
from database.base import Base


class AgentPairwiseAblationReportModel(Base):
    __tablename__ = "agent_pairwise_ablation_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class AgentPairwiseAblationReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: AgentPairwiseAblationReport) -> None:
        row = AgentPairwiseAblationReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(AgentPairwiseAblationReportModel)
            .order_by(AgentPairwiseAblationReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(AgentPairwiseAblationReportModel)
            .order_by(AgentPairwiseAblationReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: AgentPairwiseAblationReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
