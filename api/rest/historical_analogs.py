"""Historical Analog Engine API — FIL Faz D.

services/historical_analog_gatherer.py::gather_historical_analogs()
gerçek zamanlı çağrılır — Causal Inference/Agent Combination Reliability
API'sindeki desenle AYNI: hiçbir şey önceden hesaplanıp saklanmaz, her
istek gerçek kapanmış işlemlerden taze hesaplanır. Kasıtlı olarak SADECE
ölçüm/analiz — karar hattına bağlı değil (bkz. modülün kendi docstring'i)."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.historical_analog_gatherer import gather_historical_analogs

router = APIRouter(prefix="/historical-analogs", tags=["historical-analogs"])


@router.get("/")
def historical_analogs(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_historical_analogs()}
