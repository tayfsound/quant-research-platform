"""Correlation Report repository — Faz 407."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.correlation_report import CorrelationReport
from database.base import Base


class CorrelationReportModel(Base):
    __tablename__ = "correlation_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class CorrelationReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: CorrelationReport) -> None:
        row = CorrelationReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(CorrelationReportModel)
            .order_by(CorrelationReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(CorrelationReportModel)
            .order_by(CorrelationReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: CorrelationReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
