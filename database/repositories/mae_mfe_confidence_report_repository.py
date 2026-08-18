"""MAE/MFE Confidence Report repository — Cognitive Core 2.0 (Faz 469-493)."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.mae_mfe_confidence_report import MaeMfeConfidenceReport
from database.base import Base


class MaeMfeConfidenceReportModel(Base):
    __tablename__ = "mae_mfe_confidence_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class MaeMfeConfidenceReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: MaeMfeConfidenceReport) -> None:
        row = MaeMfeConfidenceReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(MaeMfeConfidenceReportModel)
            .order_by(MaeMfeConfidenceReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(MaeMfeConfidenceReportModel)
            .order_by(MaeMfeConfidenceReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: MaeMfeConfidenceReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
