"""Agent Ablation API — Faz 296.

services/agent_ablation_gatherer.py::gather_agent_ablation() gerçek
zamanlı çağrılır — diğer Grup B modülleriyle AYNI desen."""
from fastapi import APIRouter, Depends

from services.agent_ablation_gatherer import gather_agent_ablation
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/agent-ablation", tags=["agent-ablation"])


@router.get("/")
def agent_ablation(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_agent_ablation()}


@router.get("/reports")
def agent_ablation_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.agent_ablation_report_repository import (
        AgentAblationReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = AgentAblationReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
