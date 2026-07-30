"""Orchestrator API."""
from fastapi import APIRouter
from pydantic import BaseModel
from services.orchestrator import CognitiveOrchestrator

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])
_orchestrator = CognitiveOrchestrator()

class CycleRequest(BaseModel):
    seed: int = 42
    symbol: str | None = None

@router.post("/cycle")
async def run_cycle(req: CycleRequest):
    result = _orchestrator.run_cycle(seed=req.seed, symbol=req.symbol)
    return result

@router.get("/status")
async def status():
    return {"status": "ok", "version": "1.0.0"}

@router.get("/metrics")
async def metrics():
    return {
        "memory_size": len(_orchestrator.memory.memory),
        "max_position_size": _orchestrator.max_position_size,
    }
