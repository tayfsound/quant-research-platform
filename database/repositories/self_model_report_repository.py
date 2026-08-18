"""Self-Model Report repository — Cognitive Core 3.0."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.self_model_report import SelfModelReport
from database.base import Base


class SelfModelReportModel(Base):
    __tablename__ = "self_model_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class SelfModelReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: SelfModelReport) -> None:
        row = SelfModelReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(SelfModelReportModel)
            .order_by(SelfModelReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(SelfModelReportModel)
            .order_by(SelfModelReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: SelfModelReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
