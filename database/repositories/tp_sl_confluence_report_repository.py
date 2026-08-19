"""TP/SL Confluence Report repository — Faz 299-300."""
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.tp_sl_confluence_report import TpSlConfluenceReport
from database.base import Base


class TpSlConfluenceReportModel(Base):
    __tablename__ = "tp_sl_confluence_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    result = Column(JSONB, nullable=True)


class TpSlConfluenceReportRepository:
    def __init__(self, session):
        self.session = session

    def save(self, report: TpSlConfluenceReport) -> None:
        row = TpSlConfluenceReportModel(
            id=report.id,
            created_at=report.created_at,
            result=report.result,
        )
        self.session.add(row)
        self.session.commit()

    def get_latest(self) -> dict | None:
        row = (
            self.session.query(TpSlConfluenceReportModel)
            .order_by(TpSlConfluenceReportModel.created_at.desc())
            .first()
        )
        return self._to_dict(row) if row else None

    def get_recent(self, limit: int = 20) -> list[dict]:
        rows = (
            self.session.query(TpSlConfluenceReportModel)
            .order_by(TpSlConfluenceReportModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(row: TpSlConfluenceReportModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "result": row.result,
        }
