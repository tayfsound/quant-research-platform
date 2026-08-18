"""Orchestrator API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from contracts.auth import Role
from market_data.ingestion.data_provider import RoutingProvider
from services.auth_service import AuthContext, get_current_user, require_role
from services.orchestrator import CognitiveOrchestrator

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])
# Faz 269-sonrası — kullanıcı bulgusu: Predictions sayfası GC=F/SI=F/^IXIC/
# AAPL gibi Binance-dışı sembollerde hiç veri getirmiyordu. Sebep: bu
# singleton varsayılan data_provider'la (get_ohlcv_provider() -> düz
# BinanceProvider) kuruluyordu, sembol formatına bakmaksızın her şeyi
# Binance'e gönderiyordu. Gerçek trading cycle görevleri (services/tasks.py)
# zaten RoutingProvider kullanıyor — aynı yönlendirme burada da lazım.
_orchestrator = CognitiveOrchestrator(data_provider=RoutingProvider())

class CycleRequest(BaseModel):
    seed: int = 42
    symbol: str | None = None

@router.post("/cycle")
def run_cycle(req: CycleRequest, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    result = _orchestrator.run_cycle(seed=req.seed, symbol=req.symbol)
    return result

@router.get("/status")
def status(user: AuthContext = Depends(get_current_user)):
    return {"status": "ok", "version": "1.0.0"}

@router.get("/metrics")
def metrics(user: AuthContext = Depends(get_current_user)):
    return {
        "memory_size": len(_orchestrator.memory.memory),
        "max_position_size": _orchestrator.max_position_size,
    }
