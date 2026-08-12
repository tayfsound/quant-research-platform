"""Faz 250: GET /api/v1/experiments/{name}/evaluate."""
from unittest.mock import patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_evaluate_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/experiments/some_experiment/evaluate")
        assert response.status_code in (401, 403)


def test_evaluate_returns_insufficient_data_for_an_unknown_experiment():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get(
            "/api/v1/experiments/never_run_experiment_xyz/evaluate",
            headers=make_authed_headers(Role.VIEWER),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "insufficient_data"
        assert body["control_sample_count"] == 0
        assert body["treatment_sample_count"] == 0
