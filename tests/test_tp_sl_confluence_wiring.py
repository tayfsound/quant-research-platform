"""GET /api/v1/tp-sl-confluence — Faz 299-300. TP/SL Confluence'ın
gözlem/izleme katmanı — RiskTargetStage'in canlı hedef-sıkılaştırma
mantığı zaten wire edilmiş durumda (bkz. tests/test_risk_target_stage.py),
bu sadece izleme raporu."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_tp_sl_confluence_requires_auth():
    client = _client()
    response = client.get("/api/v1/tp-sl-confluence/")
    assert response.status_code in (401, 403)


def test_tp_sl_confluence_reports_endpoint_requires_auth():
    client = _client()
    response = client.get("/api/v1/tp-sl-confluence/reports")
    assert response.status_code in (401, 403)


def test_tp_sl_confluence_reports_endpoint_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/tp-sl-confluence/reports?limit=5", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "reports" in response.json()
