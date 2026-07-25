"""Decision Audit REST endpoint."""
from uuid import UUID

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])

# Stub: Gerçek repository bağlanana kadar
@router.get("/trades/{trade_id}")
async def get_trade_audit(trade_id: UUID):
    return {"trade_id": str(trade_id), "status": "Audit service active (stub)"}

@router.get("/trades")
async def list_trades(symbol: str = "BTCUSDT", limit: int = 100):
    return {"symbol": symbol, "trades": [], "count": 0}
