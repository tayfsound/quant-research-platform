"""Dashboard API."""
from fastapi import APIRouter
from services.orchestrator import CognitiveOrchestrator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_orch = CognitiveOrchestrator()

@router.get("/latest")
async def latest_cycle():
    result = _orch.run_cycle(seed=42)
    return {
        "direction": result.get("direction"),
        "pnl": result.get("pnl"),
        "win": result.get("win"),
        "risk_verdict": result.get("risk_verdict"),
        "memory_size": result.get("memory_size"),
    }

@router.get("/health")
async def health():
    return {"status": "ok", "tests": 222}
