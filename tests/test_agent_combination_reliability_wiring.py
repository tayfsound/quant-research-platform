"""GET /api/v1/agent-combination-reliability — Faz 331. Opportunity
Quality'nin "kaç ajan anlaştı" sorusunun tamamlayıcısı: "hangi ajan
İKİLİLERİ birlikte anlaştı."""
from unittest.mock import patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_agent_combination_reliability_requires_auth():
    client = _client()
    response = client.get("/api/v1/agent-combination-reliability/")
    assert response.status_code in (401, 403)


def test_agent_combination_reliability_returns_real_shape_and_is_json_serializable():
    client = _client()
    response = client.get("/api/v1/agent-combination-reliability/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "pairs" in result
    assert "baseline_win_rate" in result
    assert "n_trades" in result
    for pair in result["pairs"]:
        assert isinstance(pair["domains"], list)
        assert len(pair["domains"]) == pair["combination_size"]
        assert 0.0 <= pair["win_rate"] <= 1.0
        assert isinstance(pair["fdr_significant"], bool)


def test_agent_combination_reliability_reports_requires_auth():
    client = _client()
    response = client.get("/api/v1/agent-combination-reliability/reports")
    assert response.status_code in (401, 403)


def test_agent_combination_reliability_reports_returns_saved_snapshots():
    from contracts.agent_combination_reliability_report import AgentCombinationReliabilityReport
    from database.repositories.agent_combination_reliability_report_repository import (
        AgentCombinationReliabilityReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        report = AgentCombinationReliabilityReport(
            result={
                "pairs": [{
                    "domains": ["macro", "technical"], "combination_size": 2, "sample_size": 40,
                    "win_rate": 0.95, "win_rate_delta_vs_baseline": 0.2, "fdr_significant": True,
                }],
                "baseline_win_rate": 0.75,
                "baseline_sample_size": 100,
                "n_trades": 100,
            },
        )
        AgentCombinationReliabilityReportRepository(session).save(report)

    client = _client()
    response = client.get(
        "/api/v1/agent-combination-reliability/reports", params={"limit": 5},
        headers=make_authed_headers(Role.VIEWER),
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert any(r["id"] == str(report.id) for r in reports)
    saved = next(r for r in reports if r["id"] == str(report.id))
    assert saved["result"]["baseline_win_rate"] == 0.75


def test_refresh_agent_combination_reliability_report_task_saves_a_snapshot():
    from database.repositories.agent_combination_reliability_report_repository import (
        AgentCombinationReliabilityReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.tasks import refresh_agent_combination_reliability_report_task

    fake_result = {
        "pairs": [{
            "domains": ["macro", "technical"], "combination_size": 2, "sample_size": 40,
            "win_rate": 0.95, "win_rate_delta_vs_baseline": 0.2, "fdr_significant": True,
        }],
        "baseline_win_rate": 0.75,
        "baseline_sample_size": 100,
        "n_trades": 100,
    }
    with patch(
        "services.agent_combination_reliability_gatherer.gather_agent_combination_reliability",
        return_value=fake_result,
    ):
        result = refresh_agent_combination_reliability_report_task()

    assert result["pair_count"] == 1
    with SessionFactory.get_session() as session:
        saved = AgentCombinationReliabilityReportRepository(session).get_latest()
    assert saved is not None
    assert saved["id"] == result["id"]
