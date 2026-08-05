from fastapi.testclient import TestClient
from api.main import app
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers

client = TestClient(app)

def test_dashboard_latest():
    r = client.get("/api/v1/dashboard/latest", headers=make_authed_headers(Role.OPERATOR))
    assert r.status_code == 200
    assert "direction" in r.json()

def test_dashboard_health():
    r = client.get("/api/v1/dashboard/health", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
