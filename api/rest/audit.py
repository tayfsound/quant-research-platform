"""Decision Audit REST endpoint."""
from uuid import UUID

from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])

# Stub: Gerçek repository bağlanana kadar
@router.get("/trades/{trade_id}")
def get_trade_audit(trade_id: UUID, user: AuthContext = Depends(get_current_user)):
    return {"trade_id": str(trade_id), "status": "Audit service active (stub)"}

@router.get("/trades")
def list_trades(symbol: str = "BTCUSDT", limit: int = 100, user: AuthContext = Depends(get_current_user)):
    return {"symbol": symbol, "trades": [], "count": 0}
