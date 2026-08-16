"""Feature IC Report repository — Faz 268-sonrası."""
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.feature_ic_report import FeatureICReport
from database.base import Base


class FeatureICReportModel(Base):
    __tablename__ = "feature_ic_reports"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    features = Column(JSONB, nullable=False)
    total_closed_trades = Column(Integer, default=0)


class FeatureICReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: FeatureICReport) -> None:
        row = FeatureICReportModel(
            id=report.id,
            created_at=report.created_at,
            features=report.features,
            total_closed_trades=report.total_closed_trades,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(FeatureICReportModel)
            .order_by(FeatureICReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(FeatureICReportModel)
            .order_by(FeatureICReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: FeatureICReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "features": row.features,
            "total_closed_trades": row.total_closed_trades,
        }
