"""Dashboard API."""
from fastapi import APIRouter, Depends

from contracts.auth import Role
from services.auth_service import AuthContext, get_current_user, require_role
from services.orchestrator import CognitiveOrchestrator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_orch = CognitiveOrchestrator()

@router.get("/latest")
async def latest_cycle(user: AuthContext = Depends(require_role(Role.OPERATOR))):
    result = _orch.run_cycle(seed=42)
    return {
        "direction": result.get("direction"),
        "pnl": result.get("pnl"),
        "win": result.get("win"),
        "risk_verdict": result.get("risk_verdict"),
        "memory_size": result.get("memory_size"),
    }

@router.get("/health")
async def health(user: AuthContext = Depends(get_current_user)):
    return {"status": "ok", "tests": 222}


@router.get("/concept-drift-status")
async def concept_drift_status(user: AuthContext = Depends(get_current_user)):
    """Faz 268-sonrası — kullanıcı isteği: "Concept Drift aktif olduğunda
    panelden göreyim, sistem neden pozisyon almıyor bilmeden kalmayayım."
    Aynı eşiği/hesabı kullanır (services/risk_state.py::get_concept_
    drift_diagnostics) — RiskEngine'in ne yaptığıyla dashboard'un
    gösterdiği HER ZAMAN aynı, ayrı bir kopya hesap değil."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from services.risk_state import get_concept_drift_diagnostics

    with SessionFactory.get_session() as session:
        return get_concept_drift_diagnostics(DecisionPersistor(session))
