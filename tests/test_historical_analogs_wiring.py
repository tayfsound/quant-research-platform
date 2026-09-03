"""GET /api/v1/historical-analogs — FIL Faz D. Agent Combination
Reliability'nin (services/agent_combination_reliability_gatherer.py)
"hangi ajan İKİLİLERİ birlikte anlaştı" sorusunun üçüncü eksenli hâli:
"hangi ajan kombinasyonu + hangi rejimde ne olmuş" — AYNI test deseni
(tests/test_agent_combination_reliability_wiring.py)."""
from unittest.mock import patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_historical_analogs_requires_auth():
    client = _client()
    response = client.get("/api/v1/historical-analogs/")
    assert response.status_code in (401, 403)


def test_historical_analogs_returns_real_shape_and_is_json_serializable():
    client = _client()
    response = client.get("/api/v1/historical-analogs/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "analogs" in result
    assert "baseline_win_rate" in result
    assert "n_trades" in result
    for analog in result["analogs"]:
        assert isinstance(analog["domains"], list)
        assert len(analog["domains"]) == analog["combination_size"]
        assert analog["direction"] in ("LONG", "SHORT")
        assert isinstance(analog["market_regime"], str)
        assert 0.0 <= analog["win_rate"] <= 1.0
        assert isinstance(analog["fdr_significant"], bool)
        assert isinstance(analog["gate_eligible"], bool)


def test_historical_analogs_reports_requires_auth():
    client = _client()
    response = client.get("/api/v1/historical-analogs/reports")
    assert response.status_code in (401, 403)


def test_historical_analogs_reports_returns_saved_snapshots():
    from contracts.historical_analog_report import HistoricalAnalogReport
    from database.repositories.historical_analog_report_repository import (
        HistoricalAnalogReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        report = HistoricalAnalogReport(
            result={
                "analogs": [{
                    "domains": ["macro", "technical"], "combination_size": 2, "sample_size": 40,
                    "market_regime": "bullish_low", "direction": "LONG", "reversing": False,
                    "win_rate": 0.95, "win_rate_delta_vs_baseline": 0.2, "fdr_significant": True,
                    "gate_eligible": True,
                }],
                "baseline_win_rate": 0.75,
                "baseline_sample_size": 100,
                "n_trades": 100,
            },
        )
        HistoricalAnalogReportRepository(session).save(report)

    client = _client()
    response = client.get(
        "/api/v1/historical-analogs/reports", params={"limit": 5},
        headers=make_authed_headers(Role.VIEWER),
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert any(r["id"] == str(report.id) for r in reports)
    saved = next(r for r in reports if r["id"] == str(report.id))
    assert saved["result"]["baseline_win_rate"] == 0.75


def test_refresh_historical_analog_report_task_saves_a_snapshot():
    """Faz 404-devam — gerçek bulgu: bu görev SessionFactory import'u
    eksik olduğu için Faz 394'ten (2026-08-31) beri HER çalıştığında
    NameError ile patlıyordu — historical_analog_snapshots tablosu bu
    yüzden hep boştu, hiç kimse fark etmedi çünkü bu göreve dair hiçbir
    test yoktu (agent_combination_reliability_wiring.py'nin AYNI
    deseninin buraya eklenmemiş olması)."""
    from database.repositories.historical_analog_report_repository import (
        HistoricalAnalogReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.tasks import refresh_historical_analog_report_task

    fake_result = {
        "analogs": [{
            "domains": ["macro", "technical"], "combination_size": 2, "sample_size": 40,
            "market_regime": "bullish_low", "direction": "LONG", "reversing": False,
            "win_rate": 0.95, "win_rate_delta_vs_baseline": 0.2, "fdr_significant": True,
            "gate_eligible": True,
        }],
        "baseline_win_rate": 0.75,
        "baseline_sample_size": 100,
        "n_trades": 100,
    }
    with patch(
        "services.historical_analog_gatherer.gather_historical_analogs",
        return_value=fake_result,
    ):
        result = refresh_historical_analog_report_task()

    assert result["analog_count"] == 1
    with SessionFactory.get_session() as session:
        saved = HistoricalAnalogReportRepository(session).get_latest()
    assert saved is not None
    assert saved["id"] == result["id"]
