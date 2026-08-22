"""GET /api/v1/collective-intelligence — Collective Intelligence
(Condorcet'in Jüri Teoremi), Cognitive Core 10.0. Causal Inference'tan
sonraki, council'i hiç etkilemeyen Grup B adayı."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_collective_intelligence_requires_auth():
    client = _client()
    response = client.get("/api/v1/collective-intelligence/")
    assert response.status_code in (401, 403)


def test_collective_intelligence_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/collective-intelligence/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "per_agent_accuracy" in result
    assert "agents_excluded_insufficient_data" in result
    # WAIT-only ajanlar (hiç yönlü oy vermezler) hiçbir zaman dahil edilmemeli.
    assert "time" not in result["agents_included"]
    assert "epistemology" not in result["agents_included"]
    for domain, acc in result["per_agent_accuracy"].items():
        assert 0.0 <= acc <= 1.0
        assert result["per_agent_sample_size"][domain] >= 10
        # Faz 303 — Wilson güven aralığı her dahil edilen ajan için
        # bulunmalı ve nokta tahminini kapsamalı.
        ci = result["per_agent_confidence_interval"][domain]
        assert ci["low"] <= acc <= ci["high"]


def test_collective_intelligence_reports_requires_auth():
    client = _client()
    response = client.get("/api/v1/collective-intelligence/reports")
    assert response.status_code in (401, 403)


def test_collective_intelligence_reports_returns_saved_snapshots():
    from contracts.collective_intelligence_report import CollectiveIntelligenceReport
    from database.repositories.collective_intelligence_report_repository import (
        CollectiveIntelligenceReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        report = CollectiveIntelligenceReport(
            result={"condorcet": {"collective_beats_best_individual": False, "n_agents": 8}},
        )
        CollectiveIntelligenceReportRepository(session).save(report)

    client = _client()
    response = client.get(
        "/api/v1/collective-intelligence/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert any(r["id"] == str(report.id) for r in reports)


def test_refresh_collective_intelligence_report_task_saves_a_snapshot():
    from database.repositories.collective_intelligence_report_repository import (
        CollectiveIntelligenceReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.tasks import refresh_collective_intelligence_report_task

    result = refresh_collective_intelligence_report_task()
    assert "collective_beats_best_individual" in result

    with SessionFactory.get_session() as session:
        saved = CollectiveIntelligenceReportRepository(session).get_latest()
    assert saved is not None
    assert saved["id"] == result["id"]
