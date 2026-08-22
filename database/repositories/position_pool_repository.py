"""Faz 350 — Pozisyon Havuzu / Max Confidence Modu, kalıcılık katmanı.

bkz. services/position_pool.py (havuzlama kararı + pencere seçim mantığı),
database/migrations/versions/faz350_position_pool_candidates.py (şema)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session

from database.base import Base


class PositionPoolCandidateModel(Base):
    __tablename__ = "position_pool_candidates"
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)
    confidence = Column(Float, nullable=False)
    entry_price_at_pool = Column(Float, nullable=False)
    stop_loss_distance = Column(Float, nullable=False)
    take_profit_distance = Column(Float, nullable=False)
    planned_notional_usd = Column(Float, nullable=False)
    leverage = Column(Float, nullable=False, default=1.0)
    weight_snapshot_id = Column(PGUUID(as_uuid=True), nullable=True)
    belief_snapshot_id = Column(PGUUID(as_uuid=True), nullable=True)
    pooled_at = Column(DateTime(timezone=True), nullable=False)
    window_closes_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resulting_decision_id = Column(PGUUID(as_uuid=True), nullable=True)


class PositionPoolRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, row: PositionPoolCandidateModel) -> None:
        self.session.add(row)
        self.session.commit()

    def list_due_windows(self, now: datetime) -> list[PositionPoolCandidateModel]:
        """window_closes_at <= now VE hâlâ "pending" olan tüm adaylar —
        birden fazla sembolün penceresi aynı anda kapanabildiği için
        tek sorguda hepsi çekilip services/position_pool.py sembol
        BAĞIMSIZ (her sembolün kendi penceresi) gruplanıyor."""
        return (
            self.session.query(PositionPoolCandidateModel)
            .filter(
                PositionPoolCandidateModel.status == "pending",
                PositionPoolCandidateModel.window_closes_at <= now,
            )
            .order_by(PositionPoolCandidateModel.confidence.desc())
            .all()
        )

    def mark_resolved(
        self,
        candidate_id: UUID,
        status: str,
        resolved_at: datetime,
        resulting_decision_id: UUID | None = None,
    ) -> None:
        row = self.session.query(PositionPoolCandidateModel).filter_by(id=candidate_id).first()
        if row is None:
            return
        row.status = status
        row.resolved_at = resolved_at
        row.resulting_decision_id = resulting_decision_id
        self.session.commit()
