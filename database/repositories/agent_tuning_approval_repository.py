"""Agent tuning approval repository — database/repositories/
weight_approval_repository.py ile birebir aynı desen (dedup/has_pending,
auto_reject_stale, approval_latency_metrics)."""
from datetime import datetime, timedelta

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from contracts.agent_tuning_approval import AgentTuningApproval
from database.base import Base


class AgentTuningApprovalModel(Base):
    __tablename__ = "agent_tuning_approvals"
    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    agent_id = Column(String(64), default="")
    proposed_coefficients = Column(JSON, default=dict)
    previous_coefficients = Column(JSON, default=dict)
    in_sample_sharpe = Column(Float, default=0.0)
    mean_oos_sharpe_tuned = Column(Float, default=0.0)
    mean_oos_sharpe_baseline = Column(Float, default=0.0)
    sharpe_improvement = Column(Float, default=0.0)
    sample_count = Column(Integer, default=0)
    status = Column(String(16), default="pending")
    approved_by = Column(String(64), default="")
    expires_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)


class AgentTuningApprovalRepository:
    def __init__(self, session):
        self.session = session

    def save(self, approval: AgentTuningApproval) -> None:
        row = AgentTuningApprovalModel(
            id=approval.id,
            timestamp=approval.timestamp,
            agent_id=approval.agent_id,
            proposed_coefficients=approval.proposed_coefficients,
            previous_coefficients=approval.previous_coefficients,
            in_sample_sharpe=approval.in_sample_sharpe,
            mean_oos_sharpe_tuned=approval.mean_oos_sharpe_tuned,
            mean_oos_sharpe_baseline=approval.mean_oos_sharpe_baseline,
            sharpe_improvement=approval.sharpe_improvement,
            sample_count=approval.sample_count,
            status=approval.status,
            approved_by=approval.approved_by,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
        )
        self.session.add(row)
        self.session.commit()

    def get_pending(self, limit: int = 10):
        return (
            self.session.query(AgentTuningApprovalModel)
            .filter_by(status="pending")
            .order_by(AgentTuningApprovalModel.timestamp.desc())
            .limit(limit)
            .all()
        )

    def has_pending(self, agent_id: str) -> bool:
        """weight_approval_repository.py::has_pending() ile aynı gerekçe —
        dedup kontrolü olmadan her gerçek scheduler çalışmasında (örn.
        haftalık) neredeyse aynı içerikli yeni bir onay satırı birikirdi."""
        return (
            self.session.query(AgentTuningApprovalModel)
            .filter_by(status="pending", agent_id=agent_id)
            .first()
            is not None
        )

    def get_latest_approved(self, agent_id: str) -> AgentTuningApprovalModel | None:
        return (
            self.session.query(AgentTuningApprovalModel)
            .filter_by(status="approved", agent_id=agent_id)
            .order_by(AgentTuningApprovalModel.decided_at.desc())
            .first()
        )

    def approve(self, approval_id: str, approved_by: str = "human"):
        self.session.query(AgentTuningApprovalModel).filter_by(id=approval_id).update(
            {"status": "approved", "approved_by": approved_by, "decided_at": datetime.now()}
        )
        self.session.commit()

    def reject(self, approval_id: str, approved_by: str = "human"):
        self.session.query(AgentTuningApprovalModel).filter_by(id=approval_id).update(
            {"status": "rejected", "approved_by": approved_by, "decided_at": datetime.now()}
        )
        self.session.commit()

    def auto_reject_stale(self, max_age_seconds: float = 3600) -> int:
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        rows = (
            self.session.query(AgentTuningApprovalModel)
            .filter(
                AgentTuningApprovalModel.status == "pending",
                AgentTuningApprovalModel.timestamp < cutoff,
            )
            .all()
        )
        for row in rows:
            row.status = "rejected"
            row.decided_at = datetime.now()
        self.session.commit()
        return len(rows)
