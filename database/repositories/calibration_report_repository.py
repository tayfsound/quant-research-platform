"""Calibration Report (ECE) repository — Cognitive Core 2.0 / M4."""
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.calibration_report import CalibrationReport
from database.base import Base


class CalibrationReportModel(Base):
    __tablename__ = "calibration_reports"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)
    total_closed_trades = Column(Integer, default=0)


class CalibrationReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: CalibrationReport) -> None:
        row = CalibrationReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
            total_closed_trades=report.total_closed_trades,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(CalibrationReportModel)
            .order_by(CalibrationReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(CalibrationReportModel)
            .order_by(CalibrationReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: CalibrationReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
            "total_closed_trades": row.total_closed_trades,
        }
