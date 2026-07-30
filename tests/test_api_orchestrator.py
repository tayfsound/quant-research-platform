from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_status():
    r = client.get("/api/v1/orchestrator/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_metrics():
    r = client.get("/api/v1/orchestrator/metrics")
    assert r.status_code == 200
    assert "memory_size" in r.json()

def test_cycle():
    r = client.post("/api/v1/orchestrator/cycle", json={"seed": 42})
    assert r.status_code == 200
    data = r.json()
    assert "direction" in data
    assert "risk_verdict" in data
