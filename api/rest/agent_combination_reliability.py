"""Agent Combination Reliability API — Faz 331.

services/agent_combination_reliability_gatherer.py::gather_agent_
combination_reliability() gerçek zamanlı çağrılır — Causal Inference/
Self-Model API'sindeki desenle AYNI: hiçbir şey önceden hesaplanıp
saklanmaz, her istek gerçek kapanmış işlemlerden taze hesaplanır."""
from fastapi import APIRouter, Depends

from services.agent_combination_reliability_gatherer import gather_agent_combination_reliability
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/agent-combination-reliability", tags=["agent-combination-reliability"])


@router.get("/")
def agent_combination_reliability(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_agent_combination_reliability()}


@router.get("/reports")
def agent_combination_reliability_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Yukarıdaki / (canlı, her istekte taze) her zaman O ANKİ durumu
    gösterir. services/tasks.py::refresh_agent_combination_reliability_
    report_task'ın haftalık kaydettiği anlık görüntüler."""
    from database.repositories.agent_combination_reliability_report_repository import (
        AgentCombinationReliabilityReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = AgentCombinationReliabilityReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
