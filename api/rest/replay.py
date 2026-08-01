"""Replay API router — Faz 162."""
from fastapi import APIRouter
from services.replay_engine import ReplayEngine

router = APIRouter(prefix="/replay", tags=["replay"])

@router.get("/sessions")
async def list_sessions(limit: int = 100):
    engine = ReplayEngine()
    return {"sessions": engine.list_available_sessions(limit=limit)}

@router.post("/{session_id}")
async def run_replay(session_id: str, symbol: str = None):
    engine = ReplayEngine()
    return engine.run_replay(session_id, symbol=symbol)
