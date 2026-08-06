"""Faz 188: GET/POST /api/v1/settings — kullanıcının risk/mod ayarlarını
gerçekten değiştirebildiğini doğrular (ADMIN-yazma, herkes-okuma)."""
from unittest.mock import patch

from contracts.auth import Role
from database.repositories.app_settings_repository import DEFAULTS, AppSettingsRepository
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


def test_reset_defaults_restores_the_reasoned_trading_economics_values():
    """Faz 215: kullanıcı isteği — tek tuşla, komisyona ezilmeden $1-5
    net kâr hedefleyecek matematiksel varsayılanlara dönüş."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            client.post(
                "/api/v1/settings/starting_capital",
                params={"value": "999999999999"},
                headers=make_authed_headers(Role.ADMIN),
            )
            response = client.post(
                "/api/v1/settings/reset-defaults",
                headers=make_authed_headers(Role.ADMIN),
            )
            assert response.status_code == 200
            with SessionFactory.get_session() as session:
                repo = AppSettingsRepository(session)
                assert repo.get("starting_capital") == DEFAULTS["starting_capital"]
                assert repo.get("candle_timeframe") == DEFAULTS["candle_timeframe"]
                assert repo.get("min_profit_target_pct") == DEFAULTS["min_profit_target_pct"]
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "starting_capital", DEFAULTS["starting_capital"], updated_by="test",
                )


def test_invalid_max_capital_pct_out_of_range_rejected():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/max_capital_pct",
            params={"value": "1.5"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400


def test_display_currency_accepts_try_and_rejects_unknown_value():
    """Faz 224: kullanıcı isteği — PnL/fiyatları USD dışında (BTC/TRY)
    görebilme."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            ok = client.post(
                "/api/v1/settings/display_currency",
                params={"value": "TRY"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok.status_code == 200
            with SessionFactory.get_session() as session:
                assert AppSettingsRepository(session).get("display_currency") == "TRY"

            bad = client.post(
                "/api/v1/settings/display_currency",
                params={"value": "EUR"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad.status_code == 400
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "display_currency", DEFAULTS["display_currency"], updated_by="test",
                )


def test_currency_rates_endpoint_returns_real_live_rates():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get(
            "/api/v1/settings/currency-rates", headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["usd_btc"] > 0
        assert body["usd_try"] > 0
