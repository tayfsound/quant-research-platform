"""Kubernetes-style health checks: /health, /ready, /live.

Sprint 28: /ready used to unconditionally return "ready" regardless of
whether the DB (or anything else) was actually reachable — a K8s readiness
probe wired to that would happily route traffic to a pod that can't serve
any real request. Now it does a real `SELECT 1` and reports 503 if the DB
isn't reachable, which is the entire point of a readiness probe: keep a pod
out of the load-balancer rotation until it can actually do its job.
"""
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from version import SYSTEM_VERSION

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    checks: dict[str, bool] = {}

_startup_time = datetime.now()

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version=SYSTEM_VERSION, timestamp=datetime.now().isoformat())

@router.get("/ready", response_model=HealthResponse)
async def ready(response: Response):
    checks = {"database": _check_database()}
    all_ok = all(checks.values())
    response.status_code = 200 if all_ok else 503
    return HealthResponse(
        status="ready" if all_ok else "not_ready",
        version=SYSTEM_VERSION,
        timestamp=datetime.now().isoformat(),
        checks=checks,
    )

@router.get("/live", response_model=HealthResponse)
async def live():
    # Liveness deliberately does NOT check the DB — a DB outage should
    # fail readiness (stop new traffic), not liveness (which would make
    # Kubernetes kill and restart a perfectly healthy process for a
    # problem restarting it can't fix).
    return HealthResponse(
        status="alive",
        version=SYSTEM_VERSION,
        timestamp=datetime.now().isoformat(),
    )


def _check_database() -> bool:
    try:
        from database.connection import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
