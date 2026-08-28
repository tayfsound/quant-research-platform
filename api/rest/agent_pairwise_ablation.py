"""Agent Interaction (pairwise ablation) API — Faz 368-devam.

services/agent_pairwise_ablation_gatherer.py::gather_agent_pairwise_
ablation() gerçek zamanlı çağrılır — agent_ablation API'siyle AYNI desen."""
from fastapi import APIRouter, Depends

from services.agent_pairwise_ablation_gatherer import gather_agent_pairwise_ablation
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/agent-pairwise-ablation", tags=["agent-pairwise-ablation"])


@router.get("/")
def agent_pairwise_ablation(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_agent_pairwise_ablation()}


@router.get("/reports")
def agent_pairwise_ablation_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.agent_pairwise_ablation_report_repository import (
        AgentPairwiseAblationReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = AgentPairwiseAblationReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
