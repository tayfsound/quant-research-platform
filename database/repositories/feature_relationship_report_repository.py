"""Feature Relationship Report repository — Faz 368."""
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.feature_relationship_report import FeatureRelationshipReport
from database.base import Base


class FeatureRelationshipReportModel(Base):
    __tablename__ = "feature_relationship_reports"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    redundancy = Column(JSONB, nullable=False)
    conditional_ic = Column(JSONB, nullable=False)
    total_closed_trades = Column(Integer, default=0)


class FeatureRelationshipReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: FeatureRelationshipReport) -> None:
        row = FeatureRelationshipReportModel(
            id=report.id,
            created_at=report.created_at,
            redundancy=report.redundancy,
            conditional_ic=report.conditional_ic,
            total_closed_trades=report.total_closed_trades,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(FeatureRelationshipReportModel)
            .order_by(FeatureRelationshipReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(FeatureRelationshipReportModel)
            .order_by(FeatureRelationshipReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: FeatureRelationshipReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "redundancy": row.redundancy,
            "conditional_ic": row.conditional_ic,
            "total_closed_trades": row.total_closed_trades,
        }
