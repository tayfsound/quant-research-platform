"""Weight approval API — Faz 160 runtime."""
from datetime import datetime

from fastapi import APIRouter, Depends
from database.session_factory import SessionFactory
from database.repositories.weight_approval_repository import WeightApprovalRepository, WeightApprovalModel
from contracts.auth import Role
from services.auth_service import AuthContext, require_role

router = APIRouter(prefix="/weights", tags=["weights"])

@router.get("/pending")
async def list_pending(limit: int = 10):
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        rows = repo.get_pending(limit=limit)
        return {
            "pending": [
                {
                    "id": str(r.id),
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "proposed": r.proposed_weights,
                    "previous": r.previous_weights,
                    "max_delta": r.max_delta,
                    "regime": r.regime,
                    "status": r.status,
                }
                for r in rows
            ]
        }

@router.post("/{approval_id}/approve")
async def approve(approval_id: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        approval = session.query(WeightApprovalModel).filter_by(id=approval_id).first()
        if not approval:
            return {"error": "not_found"}
        if approval.status != "pending":
            return {"error": "already_processed", "status": approval.status}

        # Apply proposed weights to repository
        from contracts.agent_weight_snapshot import AgentWeightSnapshot
        from services.weight_repository import WeightRepository
        snapshot = AgentWeightSnapshot(
            weights=approval.proposed_weights,
            evaluation_window=100,
            previous_snapshot_id=None,
            regime=approval.regime,
        ).finalize()
        WeightRepository().save(snapshot)

        # approved_by is the AUTHENTICATED caller's username, not a free-text
        # query param anyone could fill in with anything — audit integrity
        # depends on this actually being who did it.
        repo.approve(approval_id, user.username)
        return {"approval_id": approval_id, "status": "approved", "weights_applied": True}

@router.post("/{approval_id}/reject")
async def reject(approval_id: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    with SessionFactory.get_session() as session:
        approval = session.query(WeightApprovalModel).filter_by(id=approval_id).first()
        if not approval:
            return {"error": "not_found", "approval_id": approval_id}
        if approval.status != "pending":
            return {"error": "already_processed", "approval_id": approval_id, "status": approval.status}
        session.query(WeightApprovalModel).filter_by(id=approval_id).update({"status": "rejected", "decided_at": datetime.now()})
        session.commit()
        return {"approval_id": approval_id, "status": "rejected"}


@router.post("/auto-reject")
async def auto_reject_stale(max_age_hours: float = 24, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    """Reject pending approvals older than max_age_hours."""
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        count = repo.auto_reject_stale(max_age_seconds=max_age_hours * 3600)
        return {"rejected_count": count, "max_age_hours": max_age_hours}


@router.get("/metrics")
async def approval_metrics():
    """Approval latency metrics."""
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        metrics = repo.approval_latency_metrics()
        pending_count = session.query(WeightApprovalModel).filter_by(status="pending").count()
        return {"latency": metrics, "pending_count": pending_count}
