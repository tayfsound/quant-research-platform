from fastapi import APIRouter, Depends

from contracts.auth import Role
from contracts.context import CognitiveCycleContext
from database.repositories.risk_limit_repository import load_active_limits
from services.auth_service import AuthContext, require_role
from services.cognitive_engine import CognitiveEngine

router = APIRouter(prefix="/cognitive", tags=["cognitive"])

engine = CognitiveEngine()


@router.post("/run")
async def run_cognitive_cycle(user: AuthContext = Depends(require_role(Role.OPERATOR))):
    ctx = CognitiveCycleContext()
    # Gap #15: ctx.risk.limits used to always be empty here, so RiskEngine
    # rejected every real decision with MISSING_LIMIT. Loads the ADMIN-approved
    # limits set via POST /risk-limits (see api/rest/risk_limits.py). If none
    # have ever been set, limits stays empty and MISSING_LIMIT is the correct,
    # intentional fail-closed behavior (a fresh deployment must not silently
    # approve trades against no real limit).
    ctx.risk.limits = load_active_limits()
    result = engine.run(ctx)

    return {
        "cycle_id": str(result.cycle_id),
        "action": str(result.decision.action),
        "direction": result.decision.proposed_direction,
        "confidence": result.decision.confidence,
        "uncertainty": result.decision.uncertainty,
        "knowledge": result.cognition.relevant_knowledge,
        "risk_verdict": result.risk.evaluation.verdict,
        "risk_reasons": [r.code for r in result.risk.evaluation.reasons],
    }
