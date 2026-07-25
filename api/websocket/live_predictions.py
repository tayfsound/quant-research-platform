"""Canlı tahminleri dashboard'a WebSocket ile gönderir."""
import asyncio

from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/stream/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()
    # Demo: her 2 saniyede bir rastgele tahmin gönder
    import random
    while True:
        await asyncio.sleep(2)
        direction = random.choice([-1, 0, 1])
        await websocket.send_json({
            "symbol": "BTCUSDT",
            "direction": direction,
            "confidence": round(random.uniform(0.5, 0.95), 2),
            "features": {
                "rsi": round(random.uniform(30, 70), 1),
                "macd": round(random.uniform(-10, 10), 2),
            }
        })
