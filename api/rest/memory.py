"""Memory REST endpoint — semantic search."""
from fastapi import APIRouter, Query

from services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])
memory_service = MemoryService()

@router.get("/stats")
async def memory_stats():
    return memory_service.stats()

@router.get("/episodes")
async def recent_episodes(limit: int = 50):
    return memory_service.get_recent_episodes(limit)

@router.get("/beliefs")
async def beliefs():
    return memory_service.get_beliefs()

@router.get("/similar")
async def similar_episodes(
    rsi: float = Query(default=50),
    atr: float = Query(default=1),
    volatility: float = Query(default=0.02),
    symbol: str | None = None,
    limit: int = 10,
):
    """Feature vektörüne benzeyen geçmiş episode'ları bul."""
    features = {"RSI": rsi, "ATR": atr, "volatility": volatility}
    return memory_service.find_similar(features, symbol, limit)
