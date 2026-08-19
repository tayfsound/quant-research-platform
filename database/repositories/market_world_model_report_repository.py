"""Market World Model Report repository — Cognitive Core 5.0-6.0 (Faz 901-940)."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.market_world_model_report import MarketWorldModelReport
from database.base import Base


class MarketWorldModelReportModel(Base):
    __tablename__ = "market_world_model_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class MarketWorldModelReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: MarketWorldModelReport) -> None:
        row = MarketWorldModelReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(MarketWorldModelReportModel)
            .order_by(MarketWorldModelReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(MarketWorldModelReportModel)
            .order_by(MarketWorldModelReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: MarketWorldModelReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
