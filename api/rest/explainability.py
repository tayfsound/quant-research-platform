"""Explainability API — Sprint 16."""
from fastapi import APIRouter, Depends, HTTPException

from database.repositories.belief_repository import BeliefRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user
from services.explainability import ExplainabilityService
from services.weight_repository import WeightRepository

router = APIRouter(prefix="/decisions", tags=["explainability"])


@router.get("/{decision_id}/explain")
async def explain_decision(decision_id: str, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        service = ExplainabilityService(
            decision_repo=DecisionPersistor(session),
            belief_repo=BeliefRepository(session),
            weight_repo=WeightRepository(),
        )
        result = service.explain(decision_id)
        if result is None:
            raise HTTPException(status_code=404, detail="decision_not_found")
        return result
