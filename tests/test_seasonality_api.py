"""GET /api/v1/seasonality/ — Seasonality Detection (saat/gün bazlı gerçek performans)."""
from unittest.mock import patch


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_seasonality_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/seasonality/")
        assert response.status_code in (401, 403)


def test_seasonality_endpoint_returns_the_expected_shape():
    """analytics/seasonality.py'nin algoritmik doğruluğu tests/test_
    seasonality.py'nin izole birim testlerinde zaten kanıtlanmış — burada
    sadece uç noktanın gerçekten çağırıp tutarlı bir şekil ürettiğini
    doğruluyoruz."""
    from tests.auth_helpers import make_authed_headers

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/seasonality/", headers=make_authed_headers())
        assert response.status_code == 200
        data = response.json()
        assert "hourly" in data and "buckets" in data["hourly"] and "significance" in data["hourly"]
        assert "day_of_week" in data and "buckets" in data["day_of_week"]
