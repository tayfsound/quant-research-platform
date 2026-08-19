"""Direction Prediction v2 Report repository — Cognitive Core 2.0 / M4 (Faz 519-543)."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.direction_prediction_v2_report import DirectionPredictionV2Report
from database.base import Base


class DirectionPredictionV2ReportModel(Base):
    __tablename__ = "direction_prediction_v2_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class DirectionPredictionV2ReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: DirectionPredictionV2Report) -> None:
        row = DirectionPredictionV2ReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(DirectionPredictionV2ReportModel)
            .order_by(DirectionPredictionV2ReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(DirectionPredictionV2ReportModel)
            .order_by(DirectionPredictionV2ReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: DirectionPredictionV2ReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
