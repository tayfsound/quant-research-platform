"""Health check endpoint testleri."""
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_ready():
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

def test_live():
    resp = client.get("/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"

def test_metrics():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "llm_requests_total" in resp.text
