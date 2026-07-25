"""WebSocket canlı karar akışı."""
import asyncio

from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/stream/decisions")
async def decision_stream(websocket: WebSocket):
    await websocket.accept()
    while True:
        await asyncio.sleep(2)
        await websocket.send_json({
            "verdict": "approved",
            "strategy_id": "test",
            "symbol": "BTCUSDT",
            "direction": 1,
            "confidence": 0.82,
        })
