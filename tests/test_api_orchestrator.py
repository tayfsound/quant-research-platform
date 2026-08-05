from fastapi.testclient import TestClient
from api.main import app
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers

client = TestClient(app)

def test_status():
    r = client.get("/api/v1/orchestrator/status", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_metrics():
    r = client.get("/api/v1/orchestrator/metrics", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert "memory_size" in r.json()

def test_cycle():
    r = client.post(
        "/api/v1/orchestrator/cycle",
        json={"seed": 42},
        headers=make_authed_headers(Role.OPERATOR),
    )
    assert r.status_code == 200
    data = r.json()
    assert "direction" in data
    assert "risk_verdict" in data
