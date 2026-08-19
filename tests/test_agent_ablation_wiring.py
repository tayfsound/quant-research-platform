"""GET /api/v1/agent-ablation — Faz 296. Kullanıcı isteği (2026-08-19):
mevcut auto-bench sadece davranışsal doğruluk ölçüyordu, gerçek
leave-one-out nedensel katkı ölçümü yoktu — bu, o boşluğu kapatan Grup B
modülü (council'i hiç etkilemeyen salt ölçüm/rapor katmanı)."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_agent_ablation_requires_auth():
    client = _client()
    response = client.get("/api/v1/agent-ablation/")
    assert response.status_code in (401, 403)


def test_agent_ablation_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/agent-ablation/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "by_domain" in result
    assert "n_decisions_analyzed" in result


def test_agent_ablation_reports_endpoint_requires_auth():
    client = _client()
    response = client.get("/api/v1/agent-ablation/reports")
    assert response.status_code in (401, 403)


def test_agent_ablation_reports_endpoint_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/agent-ablation/reports?limit=5", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "reports" in response.json()


def test_gather_agent_ablation_reads_real_closed_decisions():
    from services.agent_ablation_gatherer import gather_agent_ablation

    result = gather_agent_ablation()
    assert "by_domain" in result
    assert result["n_decisions_analyzed"] >= 0
