"""GET /api/v1/feature-registry/ — Faz 294 (Cognitive Core 2.0 / M1)."""
from unittest.mock import patch


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_feature_registry_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/feature-registry/")
        assert response.status_code in (401, 403)


def test_feature_registry_returns_real_catalog_entries():
    from tests.auth_helpers import make_authed_headers

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/feature-registry/", headers=make_authed_headers())
        assert response.status_code == 200
        features = response.json()["features"]
        assert "hurst_exponent" in features
        assert features["hurst_exponent"]["source_function"] == "compute_quant_signals"
