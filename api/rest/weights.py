"""Weight approval API — Faz 160 runtime."""
from fastapi import APIRouter
from database.session_factory import SessionFactory
from database.repositories.weight_approval_repository import WeightApprovalRepository

router = APIRouter(prefix="/weights", tags=["weights"])

@router.get("/pending")
async def list_pending(limit: int = 10):
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        rows = repo.get_pending(limit=limit)
        return {"pending": [{"id": str(r.id), "proposed": r.proposed_weights, "previous": r.previous_weights, "status": r.status} for r in rows]}

@router.post("/{approval_id}/approve")
async def approve(approval_id: str, approved_by: str = "human"):
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        repo.approve(approval_id, approved_by)
        return {"approval_id": approval_id, "status": "approved"}

@router.post("/{approval_id}/reject")
async def reject(approval_id: str):
    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        session.query(type(repo).__bases__[0]).filter_by(id=approval_id).update({"status": "rejected"})
        session.commit()
        return {"approval_id": approval_id, "status": "rejected"}
