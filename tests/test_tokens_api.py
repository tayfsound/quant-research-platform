"""Faz 207: /tokens API — dashboard'un watchlist'teki tüm sembolleri tek
ekranda gösterebilmesi için (Predictions.tsx sadece tek sembol gösteriyordu)."""
from unittest.mock import patch

from contracts.auth import Role
from database.repositories.app_settings_repository import AppSettingsRepository, DEFAULTS
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_list_tokens_returns_every_watchlist_symbol():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("watchlist", "BTCUSDT,AAPL", updated_by="test")
        try:
            client = _client()
            response = client.get("/api/v1/tokens/", headers=make_authed_headers(Role.VIEWER))
            assert response.status_code == 200
            symbols = {t["symbol"] for t in response.json()["tokens"]}
            assert symbols == {"BTCUSDT", "AAPL"}
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("watchlist", DEFAULTS["watchlist"], updated_by="test")


def test_token_detail_404s_for_symbol_not_in_watchlist():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/tokens/NOTREAL", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 404


def test_risk_profile_reports_a_max_safe_leverage_below_liquidation_risk():
    """Faz 260: kullanıcı bulgusu — yüksek kaldıraç + geniş ATR'de
    likidasyon stop-loss'tan önce tetiklenebiliyordu. Bu uç nokta,
    Tokens sayfasındaki kaldıraç diyaloğunun kullanıcıyı önceden
    uyarabilmesi için gerçek günlük ATR'den bir güvenli-kaldıraç
    tavanı hesaplıyor."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/tokens/BTCUSDT/risk-profile", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "BTCUSDT"
        if body["daily_atr_pct"] is not None:
            assert body["stop_distance_pct"] > 0
            assert 0 < body["max_safe_leverage"] <= 125.0


def test_token_detail_returns_decisions_for_watchlisted_symbol():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            watchlist = AppSettingsRepository(session).get("watchlist")
        symbol = watchlist.split(",")[0].strip()

        client = _client()
        response = client.get(f"/api/v1/tokens/{symbol}", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == symbol
        assert isinstance(body["decisions"], list)
