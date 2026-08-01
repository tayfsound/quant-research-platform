"""WebSocket canli cycle feed."""
from fastapi import WebSocket, WebSocketDisconnect
from services.orchestrator import CognitiveOrchestrator

class CycleFeedManager:
    def __init__(self):
        self.connections = []
        self.orch = CognitiveOrchestrator()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, result: dict):
        for conn in self.connections:
            try:
                await conn.send_json(result)
            except Exception:
                pass

    async def run_cycle_and_broadcast(self):
        result = self.orch.run_cycle()
        await self.broadcast(result)

manager = CycleFeedManager()

async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "run_cycle":
                await manager.run_cycle_and_broadcast()
            elif data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
