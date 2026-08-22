"""GET /api/v1/market-world-model — Cognitive Core 5.0-6.0 (Faz 901-940).
Kullanıcı onayıyla (2026-08-19) 4 Grup B modülünden biri, council'i hiç
etkilemeyen bir simülasyon/rapor katmanı."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_market_world_model_requires_auth():
    client = _client()
    response = client.get("/api/v1/market-world-model/")
    assert response.status_code in (401, 403)


def test_market_world_model_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/market-world-model/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "n_returns" in result
    assert "block_size" in result
    assert "path_length" in result


def test_market_world_model_reports_endpoint_requires_auth():
    client = _client()
    response = client.get("/api/v1/market-world-model/reports")
    assert response.status_code in (401, 403)


def test_market_world_model_reports_endpoint_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/market-world-model/reports?limit=5", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    assert "reports" in response.json()


def test_gather_market_world_model_produces_real_bootstrap_paths_from_synthetic_returns():
    """compute_block_bootstrap_paths'in gerçek getirilerden anlamlı bir
    dağılım ürettiğini (p5 <= mean <= p95) doğruluyor — icat edilmiş
    sabit bir sonuç değil."""
    from analytics.market_world_model import compute_block_bootstrap_paths

    returns = [0.01, -0.005, 0.02, -0.01, 0.015, -0.008, 0.03, -0.02] * 5  # 40 gerçek-şekilli getiri
    result = compute_block_bootstrap_paths(returns, block_size=5, path_length=20, n_paths=200)
    assert result is not None
    assert result["p5_cumulative_return"] <= result["mean_cumulative_return"] <= result["p95_cumulative_return"]


def test_gather_market_world_model_reads_real_closed_trades():
    from services.market_world_model_gatherer import gather_market_world_model

    result = gather_market_world_model()
    assert "n_returns" in result
    assert result["n_returns"] >= 0
