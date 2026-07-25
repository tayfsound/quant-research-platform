"""Kubernetes‑style health checks: /health, /ready, /live."""
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str

_startup_time = datetime.now()

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="0.15.5", timestamp=datetime.now().isoformat())

@router.get("/ready", response_model=HealthResponse)
async def ready():
    # LLM'in yanıt verip vermediğini kontrol et (opsiyonel)
    return HealthResponse(status="ready", version="0.15.5", timestamp=datetime.now().isoformat())

@router.get("/live", response_model=HealthResponse)
async def live():
    uptime_seconds = (datetime.now() - _startup_time).total_seconds()
    return HealthResponse(
        status="alive",
        version="0.15.5",
        timestamp=datetime.now().isoformat(),
    )
