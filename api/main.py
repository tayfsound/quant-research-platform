"""FastAPI ana uygulama — tum router'lar."""
import time

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api.rest import agents, audit, auth, backtest, cognitive, dashboard, explainability, market_data, memory, models, orchestrator, positions, replay, risk_limits, settings, strategies, tokens, weights, webhooks, workspace
from api.websocket.cycle_feed import websocket_endpoint
from observability.health import router as health_router
from observability.metrics import api_request_latency_seconds, api_requests_total, get_metrics

app = FastAPI(title="AI Quant Research Platform", version="1.2.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
async def metrics():
    return Response(content=get_metrics(), media_type="text/plain")

app.include_router(replay.router, prefix="/api/v1")
app.include_router(weights.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(cognitive.router, prefix="/api/v1")
app.include_router(orchestrator.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")
app.include_router(explainability.router, prefix="/api/v1")
app.include_router(workspace.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(risk_limits.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(market_data.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(tokens.router, prefix="/api/v1")

@app.websocket("/ws/cycle")
async def cycle_websocket(websocket: WebSocket):
    await websocket_endpoint(websocket)
