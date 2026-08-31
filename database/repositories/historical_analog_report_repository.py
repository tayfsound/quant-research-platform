"""Historical Analog Report repository — Faz 394."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.historical_analog_report import HistoricalAnalogReport
from database.base import Base


class HistoricalAnalogReportModel(Base):
    __tablename__ = "historical_analog_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class HistoricalAnalogReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: HistoricalAnalogReport) -> None:
        row = HistoricalAnalogReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(HistoricalAnalogReportModel)
            .order_by(HistoricalAnalogReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(HistoricalAnalogReportModel)
            .order_by(HistoricalAnalogReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: HistoricalAnalogReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
