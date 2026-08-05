"""Strateji REST endpoint'leri."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from contracts.auth import Role
from services.auth_service import AuthContext, get_current_user, require_role

router = APIRouter(prefix="/strategies", tags=["strategies"])

@router.post("/{id}/simulate")
async def simulate_strategy(
    id: UUID,
    symbol: str,
    timeframe: str,
    capital: float,
    start: str,
    end: str,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    return {"run_id": uuid4(), "strategy_id": id, "status": "queued"}

@router.get("/{id}/results")
async def get_results(id: UUID, user: AuthContext = Depends(get_current_user)):
    return {"strategy_id": id, "sharpe": 1.5, "total_return": 0.25}
