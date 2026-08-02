"""Weight approval repository."""
from sqlalchemy import Column, String, DateTime, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from database.base import Base
from contracts.weight_approval import WeightApproval


class WeightApprovalModel(Base):
    __tablename__ = "weight_approvals"
    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    proposed_weights = Column(JSON, default=dict)
    previous_weights = Column(JSON, default=dict)
    max_delta = Column(Float, default=0.10)
    status = Column(String(16), default="pending")
    approved_by = Column(String(64), default="")


class WeightApprovalRepository:
    def __init__(self, session):
        self.session = session

    def save(self, approval: WeightApproval) -> None:
        row = WeightApprovalModel(
            id=approval.id,
            timestamp=approval.timestamp,
            proposed_weights=approval.proposed_weights,
            previous_weights=approval.previous_weights,
            max_delta=approval.max_delta,
            status=approval.status,
            approved_by=approval.approved_by,
        )
        self.session.add(row)
        self.session.commit()

    def get_pending(self, limit: int = 10):
        return self.session.query(WeightApprovalModel).filter_by(status="pending").order_by(WeightApprovalModel.timestamp.desc()).limit(limit).all()

    def approve(self, approval_id: str, approved_by: str = "human"):
        self.session.query(WeightApprovalModel).filter_by(id=approval_id).update({"status": "approved", "approved_by": approved_by})
        self.session.commit()
