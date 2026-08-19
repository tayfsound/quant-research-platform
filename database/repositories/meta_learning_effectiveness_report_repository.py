"""Meta-Learning Effectiveness Report repository — Cognitive Core 2.0 (Faz 744-768)."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.meta_learning_effectiveness_report import MetaLearningEffectivenessReport
from database.base import Base


class MetaLearningEffectivenessReportModel(Base):
    __tablename__ = "meta_learning_effectiveness_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class MetaLearningEffectivenessReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: MetaLearningEffectivenessReport) -> None:
        row = MetaLearningEffectivenessReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(MetaLearningEffectivenessReportModel)
            .order_by(MetaLearningEffectivenessReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(MetaLearningEffectivenessReportModel)
            .order_by(MetaLearningEffectivenessReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: MetaLearningEffectivenessReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
