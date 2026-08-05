"""Faz 188: GET/POST /api/v1/settings — kullanıcının risk/mod ayarlarını
gerçekten değiştirebildiğini doğrular (ADMIN-yazma, herkes-okuma)."""
from unittest.mock import patch

from contracts.auth import Role
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_get_settings_returns_defaults_when_nothing_set():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/settings/", headers=make_authed_headers(Role.VIEWER))

        assert response.status_code == 200
        body = response.json()["settings"]
        assert body["trading_mode"] in ("test", "live")
        assert "max_concurrent_positions" in body
        assert "trade_horizon" in body


def test_admin_can_set_trading_mode_and_it_persists():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/trading_mode",
            params={"value": "live"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 200

        with SessionFactory.get_session() as session:
            assert AppSettingsRepository(session).get("trading_mode") == "live"


def test_viewer_cannot_set_settings():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/trading_mode",
            params={"value": "live"},
            headers=make_authed_headers(Role.VIEWER),
        )
        assert response.status_code == 403


def test_invalid_trading_mode_value_rejected():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/trading_mode",
            params={"value": "yolo"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400


def test_invalid_max_capital_pct_out_of_range_rejected():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/max_capital_pct",
            params={"value": "1.5"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400
