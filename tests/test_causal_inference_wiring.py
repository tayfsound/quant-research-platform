"""GET /api/v1/causal-inference — Causal Inference (Granger causality),
Cognitive Core 4.0. Self-Model'den sonraki, council'i hiç etkilemeyen
Grup B adayı."""
from unittest.mock import patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_causal_inference_requires_auth():
    client = _client()
    response = client.get("/api/v1/causal-inference/")
    assert response.status_code in (401, 403)


def test_causal_inference_returns_real_shape_and_is_json_serializable():
    """Gerçek bulgu: statsmodels'in lag anahtarları numpy int64 —
    düzeltilmeden JSON serileştirmesi (ve JSONB'ye yazma) sessizce
    çöküyordu. Bu test gerçek uçtan uca HTTP round-trip'in (JSON
    serialize + parse) hatasız tamamlandığını doğruluyor."""
    client = _client()
    response = client.get("/api/v1/causal-inference/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "significant_relationships" in result
    assert "pairs_tested" in result
    for rel in result["significant_relationships"]:
        assert isinstance(rel["best_lag"], int)
        assert 0.0 <= rel["best_p_value"] < 0.05


def test_causal_inference_reports_requires_auth():
    client = _client()
    response = client.get("/api/v1/causal-inference/reports")
    assert response.status_code in (401, 403)


def test_causal_inference_reports_returns_saved_snapshots():
    from contracts.causal_inference_report import CausalInferenceReport
    from database.repositories.causal_inference_report_repository import CausalInferenceReportRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        report = CausalInferenceReport(
            result={"pairs_tested": 96, "significant_relationships": [
                {"cause": "BTCUSDT", "effect": "CHZUSDT", "best_lag": 1, "best_p_value": 0.0007, "sample_size": 199}
            ]},
        )
        CausalInferenceReportRepository(session).save(report)

    client = _client()
    response = client.get(
        "/api/v1/causal-inference/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert any(r["id"] == str(report.id) for r in reports)
    saved = next(r for r in reports if r["id"] == str(report.id))
    assert saved["result"]["pairs_tested"] == 96


def test_refresh_causal_inference_report_task_saves_a_snapshot():
    """gather_causal_relationships() gerçek ağ çağrısı yapar (fetch_
    returns) — bu yüzden tam gatherer'ı çağırmak yerine, yalnızca
    kaydetme mekanizmasını gerçek olmayan (ama gerçekçi biçimli) bir
    sonuçla izole test ediyoruz. Task içindeki import yerel olduğu için
    (çağrı anında çözülüyor) hedef modül services.causal_inference_
    gatherer, services.tasks değil."""
    from database.repositories.causal_inference_report_repository import CausalInferenceReportRepository
    from database.session_factory import SessionFactory
    from services.tasks import refresh_causal_inference_report_task

    fake_result = {"pairs_tested": 10, "significant_relationships": [
        {"cause": "BTCUSDT", "effect": "ETCUSDT", "best_lag": 2, "best_p_value": 0.01, "sample_size": 199}
    ]}
    with patch("services.causal_inference_gatherer.gather_causal_relationships", return_value=fake_result):
        result = refresh_causal_inference_report_task()

    assert result["significant_relationship_count"] == 1
    with SessionFactory.get_session() as session:
        saved = CausalInferenceReportRepository(session).get_latest()
    assert saved is not None
    assert saved["id"] == result["id"]
