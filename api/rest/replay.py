"""Replay API router — Faz 162."""
from fastapi import APIRouter, Depends

from database.repositories.belief_repository import BeliefRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user
from services.replay_engine import ReplayEngine

router = APIRouter(prefix="/replay", tags=["replay"])


def _engine(session) -> ReplayEngine:
    return ReplayEngine(
        belief_repo=BeliefRepository(session),
        decision_repo=DecisionPersistor(session),
    )


@router.get("/sessions")
async def list_sessions(limit: int = 100, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        return {"sessions": _engine(session).list_available_sessions(limit=limit)}


@router.post("/{session_id}")
async def run_replay(session_id: str, symbol: str = None, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        return _engine(session).run_replay(session_id, symbol=symbol)


@router.post("/decision/{decision_id}")
async def replay_decision(decision_id: str, deterministic: bool = True, user: AuthContext = Depends(get_current_user)):
    """Replay a single decision and verify it reproduces the same outcome
    (services/replay/ decision_hash + ReplayVerifier)."""
    with SessionFactory.get_session() as session:
        return _engine(session).replay_decision(decision_id, deterministic=deterministic)
