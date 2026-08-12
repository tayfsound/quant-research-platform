"""FastAPI ana uygulama — tum router'lar."""
import time

import os

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api.rest import agents, audit, auth, backtest, cognitive, dashboard, experiments, market_data, memory, models, orchestrator, positions, risk_limits, settings, strategies, tokens, weights, webhooks, workspace
from config import get_settings
from observability.health import router as health_router
from observability.metrics import api_request_latency_seconds, api_requests_total, get_metrics
from services.auth_service import AuthContext, get_current_user

app = FastAPI(title="AI Quant Research Platform", version="1.2.5")

# 3. taraf inceleme bulgusu (5.1) — SECRET_KEY boşsa auth hiç çalışamaz
# (services/auth_service.py::_require_secret_key ilk token işlemine kadar
# bunu fark etmiyordu — "runtime'da patlamak yerine startup'ta" doğru
# tespit). API 0.0.0.0'a bağlı (aynı ağdaki her cihaza açık) olduğu için
# boş SECRET_KEY = auth'un fiilen devre dışı kalması, sessizce.
if not get_settings().SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set — refusing to start with auth effectively disabled. "
        "Set SECRET_KEY in .env before starting the API."
    )

app.add_middleware(
    CORSMiddleware,
    # 3. taraf inceleme bulgusu (4.3) — localhost:5173 sabit kodluydu.
    # CORS_ORIGINS env değişkeniyle (virgülle ayrılmış) override edilebilir,
    # verilmezse eski davranışla (sadece local dev sunucusu) birebir aynı.
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["health"])


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Sprint 14-15: instruments EVERY endpoint at once (one wiring point,
    covers the whole API surface instead of instrumenting each router)."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    route = request.scope.get("route")
    path_label = route.path if route is not None else request.url.path

    api_requests_total.labels(
        method=request.method, path=path_label, status=str(response.status_code)
    ).inc()
    api_request_latency_seconds.labels(method=request.method, path=path_label).observe(elapsed)

    return response

@app.get("/metrics")
async def metrics(user: AuthContext = Depends(get_current_user)):
    # 3. taraf inceleme bulgusu (5.2) — auth'suzdu, API 0.0.0.0'a bağlı
    # (LAN'a açık) olduğu için aynı ağdaki biri metrikleri görebiliyordu.
    return Response(content=get_metrics(), media_type="text/plain")

app.include_router(weights.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(cognitive.router, prefix="/api/v1")
app.include_router(orchestrator.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(workspace.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(risk_limits.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(market_data.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(experiments.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(tokens.router, prefix="/api/v1")
