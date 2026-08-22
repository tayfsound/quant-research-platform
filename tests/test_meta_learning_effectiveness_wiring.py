"""GET /api/v1/meta-learning-effectiveness — Cognitive Core 2.0 / M10
(Faz 744-768). Kullanıcı onayıyla (2026-08-19) 4 Grup B modülünden biri,
council'i hiç etkilemeyen bir tespit/rapor katmanı."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_meta_learning_effectiveness_requires_auth():
    client = _client()
    response = client.get("/api/v1/meta-learning-effectiveness/")
    assert response.status_code in (401, 403)


def test_meta_learning_effectiveness_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/meta-learning-effectiveness/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "trend" in result
    assert "n_approved_rounds" in result


def test_meta_learning_effectiveness_reports_endpoint_requires_auth():
    client = _client()
    response = client.get("/api/v1/meta-learning-effectiveness/reports")
    assert response.status_code in (401, 403)


def test_meta_learning_effectiveness_reports_endpoint_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/meta-learning-effectiveness/reports?limit=5", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "reports" in response.json()


def test_gather_detects_a_real_improving_trend():
    """compute_meta_learning_trend'in MIN_ROUNDS'u (8) kadar gerçek,
    monoton artan sharpe_improvement üretip 'improving' trendini
    gerçekten yakaladığını doğruluyor — sabit bir sonuç değil."""
    from analytics.meta_learning_effectiveness import compute_meta_learning_trend

    improvements = [0.01 * i for i in range(10)]  # açıkça artan, anlamlı bir trend
    result = compute_meta_learning_trend(improvements)
    assert result is not None
    assert result["trend"] == "improving"
    assert result["n_rounds"] == 10


def test_gather_meta_learning_effectiveness_reads_real_approved_rounds():
    from services.meta_learning_effectiveness_gatherer import gather_meta_learning_effectiveness

    result = gather_meta_learning_effectiveness()
    assert "trend" in result
    assert "n_approved_rounds" in result
    assert result["n_approved_rounds"] >= 0
