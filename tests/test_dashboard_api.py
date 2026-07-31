from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_dashboard_latest():
    r = client.get("/api/v1/dashboard/latest")
    assert r.status_code == 200
    assert "direction" in r.json()

def test_dashboard_health():
    r = client.get("/api/v1/dashboard/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
