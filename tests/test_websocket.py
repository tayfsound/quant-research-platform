"""WebSocket integration testleri."""
import pytest
from fastapi.testclient import TestClient
from api.main import app

def test_websocket_ping_pong():
    """WebSocket baglantisi kurulabilmeli."""
    client = TestClient(app)
    with client.websocket_connect("/ws/cycle") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_text()
        assert data == "pong"

def test_websocket_run_cycle():
    """run_cycle mesaji sonuc donmeli."""
    client = TestClient(app)
    with client.websocket_connect("/ws/cycle") as websocket:
        websocket.send_text("run_cycle")
        data = websocket.receive_json()
        assert "direction" in data
        assert "risk_verdict" in data
