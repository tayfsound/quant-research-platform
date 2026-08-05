"""Canlı tahminleri dashboard'a WebSocket ile gönderir.

Gap #18: bu endpoint eskiden `random.choice`/`random.uniform` ile tamamen
uydurma veri üretiyordu — dashboard'un "Live AI Predictions" view'ı gerçek
bir modelin çıktısı gibi gösteriyordu ama arkasında hiçbir gerçek karar yoktu.
Artık her tick'te gerçek `CognitiveOrchestrator.run_cycle()` (aynı motor,
`/orchestrator/cycle` ve `/dashboard/latest`'in kullandığı) çalıştırılıyor.
"""
import asyncio

from fastapi import APIRouter, WebSocket

from services.orchestrator import CognitiveOrchestrator

router = APIRouter()

_DIRECTION_TO_INT = {"LONG": 1, "SHORT": -1, "NEUTRAL": 0}


@router.websocket("/stream/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()
    orch = CognitiveOrchestrator()
    while True:
        await asyncio.sleep(2)
        result = orch.run_cycle()
        features = result.get("features") or {}
        await websocket.send_json({
            "symbol": result.get("symbol"),
            "direction": _DIRECTION_TO_INT.get(result.get("direction"), 0),
            "confidence": round(result.get("confidence") or 0.0, 3),
            "features": {
                "rsi": features.get("rsi"),
                "macd": features.get("macd"),
            },
        })
