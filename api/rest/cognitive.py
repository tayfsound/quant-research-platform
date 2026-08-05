from fastapi import APIRouter, Depends

from contracts.auth import Role
from contracts.context import CognitiveCycleContext
from services.auth_service import AuthContext, require_role
from services.cognitive_engine import CognitiveEngine

router = APIRouter(prefix="/cognitive", tags=["cognitive"])

engine = CognitiveEngine()


@router.post("/run")
async def run_cognitive_cycle(user: AuthContext = Depends(require_role(Role.OPERATOR))):
    ctx = CognitiveCycleContext()
    result = engine.run(ctx)

    return {
        "cycle_id": str(result.cycle_id),
        "action": str(result.decision.action),
        "direction": result.decision.proposed_direction,
        "confidence": result.decision.confidence,
        "uncertainty": result.decision.uncertainty,
        "knowledge": result.cognition.relevant_knowledge,
    }
