"""Strategy Gate Approval API — Faz 366. api/rest/weights.py ile AYNI
desen (propose→pending→approve/reject)."""
from datetime import datetime

from fastapi import APIRouter, Depends

from contracts.auth import Role
from database.repositories.strategy_gate_approval_repository import (
    StrategyGateApprovalModel,
    StrategyGateApprovalRepository,
)
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, require_role

router = APIRouter(prefix="/strategy-gates", tags=["strategy-gates"])


@router.get("/pending")
def list_pending(limit: int = 10):
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        rows = repo.get_pending(limit=limit)
        return {
            "pending": [
                {
                    "id": str(r.id),
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "strategy": r.strategy,
                    "market_regime": r.market_regime,
                    "sample_size": r.sample_size,
                    "win_rate": r.win_rate,
                    "rest_win_rate": r.rest_win_rate,
                    "delta_vs_rest": r.delta_vs_rest,
                    "p_value": r.p_value,
                    "replicated_out_of_sample": r.replicated_out_of_sample,
                    "status": r.status,
                }
                for r in rows
            ]
        }


@router.get("/blocked")
def list_blocked():
    with SessionFactory.get_session() as session:
        rows = (
            session.query(StrategyGateApprovalModel)
            .filter_by(status="blocked")
            .order_by(StrategyGateApprovalModel.decided_at.desc())
            .all()
        )
        return {
            "blocked": [
                {
                    "id": str(r.id), "strategy": r.strategy, "market_regime": r.market_regime,
                    "win_rate": r.win_rate, "rest_win_rate": r.rest_win_rate,
                    "approved_by": r.approved_by,
                    "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                }
                for r in rows
            ]
        }


@router.post("/{approval_id}/approve")
def approve(approval_id: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    """İnsanın "bu (strateji, rejim) engellensin" kararı — sonuç durumu
    "blocked" (bkz. StrategyGateApprovalRepository.approve() docstring'i:
    onaylanan şey stratejinin iyiliği değil, engellenmesi)."""
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        approval = session.query(StrategyGateApprovalModel).filter_by(id=approval_id).first()
        if not approval:
            return {"error": "not_found"}
        if approval.status != "pending":
            return {"error": "already_processed", "status": approval.status}
        repo.approve(approval_id, user.username)
        return {"approval_id": approval_id, "status": "blocked"}


@router.post("/{approval_id}/reject")
def reject(approval_id: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    """İnsanın "bu adayı engellemeyeceğim" kararı — sonuç durumu
    "dismissed" (candidate incelendi, gate'e bağlanmadı)."""
    with SessionFactory.get_session() as session:
        approval = session.query(StrategyGateApprovalModel).filter_by(id=approval_id).first()
        if not approval:
            return {"error": "not_found", "approval_id": approval_id}
        if approval.status != "pending":
            return {"error": "already_processed", "approval_id": approval_id, "status": approval.status}
        session.query(StrategyGateApprovalModel).filter_by(id=approval_id).update(
            {"status": "dismissed", "decided_at": datetime.now()}
        )
        session.commit()
        return {"approval_id": approval_id, "status": "dismissed"}
