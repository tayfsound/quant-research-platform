"""Orchestrator API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from contracts.auth import Role
from services.auth_service import AuthContext, get_current_user, require_role
from services.orchestrator import CognitiveOrchestrator

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])
_orchestrator = CognitiveOrchestrator()

class CycleRequest(BaseModel):
    seed: int = 42
    symbol: str | None = None

@router.post("/cycle")
def run_cycle(req: CycleRequest, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    result = _orchestrator.run_cycle(seed=req.seed, symbol=req.symbol)
    return result

@router.get("/status")
def status(user: AuthContext = Depends(get_current_user)):
    return {"status": "ok", "version": "1.0.0"}

@router.get("/metrics")
def metrics(user: AuthContext = Depends(get_current_user)):
    return {
        "memory_size": len(_orchestrator.memory.memory),
        "max_position_size": _orchestrator.max_position_size,
    }
