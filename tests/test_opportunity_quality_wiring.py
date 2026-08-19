"""GET /api/v1/opportunity-quality — Cognitive Core 2.0 (Faz 569-593).
Kullanıcı onayıyla (2026-08-19) 4 Grup B modülünden biri, council'i hiç
etkilemeyen bir ölçüm/rapor katmanı."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_opportunity_quality_requires_auth():
    client = _client()
    response = client.get("/api/v1/opportunity-quality/")
    assert response.status_code in (401, 403)


def test_opportunity_quality_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/opportunity-quality/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "by_agreement_bucket" in result
    assert "n_trades" in result


def test_opportunity_quality_reports_endpoint_requires_auth():
    client = _client()
    response = client.get("/api/v1/opportunity-quality/reports")
    assert response.status_code in (401, 403)


def test_opportunity_quality_reports_endpoint_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/opportunity-quality/reports?limit=5", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "reports" in response.json()


def test_gather_opportunity_quality_reads_real_closed_trades():
    from services.opportunity_quality_gatherer import gather_opportunity_quality

    result = gather_opportunity_quality()
    assert "by_agreement_bucket" in result
    assert result["n_trades"] >= 0


def test_agreement_for_decision_extracts_real_votes_from_agent_contributions():
    from services.opportunity_quality_gatherer import _agreement_for_decision

    row = {
        "agent_contributions": [
            {"domain": "technical", "direction": "LONG"},
            {"domain": "macro", "direction": "LONG"},
            {"domain": "quant", "direction": "SHORT"},
            {"type": "market_snapshot", "data": {}},  # oy DEĞİL, göz ardı edilmeli
        ]
    }
    agreement = _agreement_for_decision(row)
    assert agreement is not None
    assert 0.0 <= agreement <= 1.0


def test_agreement_for_decision_returns_none_when_no_real_votes_present():
    from services.opportunity_quality_gatherer import _agreement_for_decision

    row = {"agent_contributions": [{"type": "market_snapshot", "data": {}}]}
    assert _agreement_for_decision(row) is None
