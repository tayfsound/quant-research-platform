"""Memory REST endpoint — semantic search."""
from fastapi import APIRouter, Depends, Query

from services.auth_service import AuthContext, get_current_user
from services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])
memory_service = MemoryService()

@router.get("/stats")
def memory_stats(user: AuthContext = Depends(get_current_user)):
    return memory_service.stats()

@router.get("/episodes")
def recent_episodes(limit: int = 50, user: AuthContext = Depends(get_current_user)):
    return memory_service.get_recent_episodes(limit)

@router.get("/beliefs")
def beliefs(user: AuthContext = Depends(get_current_user)):
    return memory_service.get_beliefs()

@router.get("/similar")
def similar_episodes(
    rsi: float = Query(default=50),
    atr: float = Query(default=1),
    volatility: float = Query(default=0.02),
    symbol: str | None = None,
    limit: int = 10,
    user: AuthContext = Depends(get_current_user),
):
    """Feature vektörüne benzeyen geçmiş episode'ları bul."""
    features = {"RSI": rsi, "ATR": atr, "volatility": volatility}
    return memory_service.find_similar(features, symbol, limit)
