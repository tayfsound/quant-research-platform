"""WebSocket integration testleri."""
import pytest
from unittest.mock import patch, MagicMock
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
    # CycleFeedManager.orch.run_cycle mock'la
    with patch("api.websocket.cycle_feed.manager.orch.run_cycle") as mock_run:
        mock_run.return_value = {
            "direction": "LONG",
            "pnl": 100.0,
            "risk_verdict": "approved",
        }
        client = TestClient(app)
        with client.websocket_connect("/ws/cycle") as websocket:
            websocket.send_text("run_cycle")
            data = websocket.receive_json()
            assert data["direction"] == "LONG"
            assert data["risk_verdict"] == "approved"
