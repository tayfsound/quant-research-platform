"""FastAPI ana uygulama — tüm router'lar."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from api.rest import strategies, models, reasoning, audit, memory, cognitive
from api.websocket import decisions, live_predictions
from observability.health import router as health_router
from observability.metrics import get_metrics

app = FastAPI(title="AI Quant Research Platform", version="0.15.5")

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

app.include_router(strategies.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(decisions.router, prefix="/api/v1")
app.include_router(live_predictions.router, prefix="/api/v1")
app.include_router(reasoning.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(cognitive.router, prefix="/api/v1")
