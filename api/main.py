"""FastAPI ana uygulama — tum router'lar."""
from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api.rest import audit, cognitive, dashboard, experiments, memory, models, orchestrator, reasoning, replay, strategies, weights
from api.websocket import decisions, live_predictions
from api.websocket.cycle_feed import websocket_endpoint
from observability.health import router as health_router
from observability.metrics import get_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pending outcome scheduler
    from services.pending_outcome_tracker import PendingOutcomeTracker
    tracker = PendingOutcomeTracker()
    # TODO: real data_provider + symbol/timeframe config
    # asyncio.create_task(tracker.run_scheduler(...))
    yield
    # Shutdown

app = FastAPI(title="AI Quant Research Platform", version="1.2.5", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["health"])

@app.get("/metrics")
async def metrics():
    return Response(content=get_metrics(), media_type="text/plain")

app.include_router(replay.router, prefix="/api/v1")
app.include_router(weights.router, prefix="/api/v1")
app.include_router(experiments.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(decisions.router, prefix="/api/v1")
app.include_router(live_predictions.router, prefix="/api/v1")
app.include_router(reasoning.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(cognitive.router, prefix="/api/v1")
app.include_router(orchestrator.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")

@app.websocket("/ws/cycle")
async def cycle_websocket(websocket: WebSocket):
    await websocket_endpoint(websocket)
