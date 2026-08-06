"""Faz 214: kullanıcı isteği ("4 saatlik verileri kullanmak daha isabetli
olmaz mı, geçmiş pencere çok kısa") — candle_timeframe/candle_lookback
artık app_settings üzerinden gerçekten kontrol edilebiliyor, hem
CognitiveOrchestrator hem de /cognitive/run (Faz 206'nın ikinci, unutulmuş
kopyası) bunu okuyor."""
from unittest.mock import patch

from contracts.auth import Role
from database.repositories.app_settings_repository import AppSettingsRepository, DEFAULTS
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_invalid_candle_timeframe_rejected():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/candle_timeframe",
            params={"value": "7h"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400


def test_candle_lookback_out_of_range_rejected():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/candle_lookback",
            params={"value": "5"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400


def test_admin_can_set_candle_timeframe_and_it_persists():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            response = client.post(
                "/api/v1/settings/candle_timeframe",
                params={"value": "4h"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert response.status_code == 200
            with SessionFactory.get_session() as session:
                assert AppSettingsRepository(session).get("candle_timeframe") == "4h"
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "candle_timeframe", DEFAULTS["candle_timeframe"], updated_by="test",
                )


def test_orchestrator_build_context_uses_configured_timeframe_and_lookback():
    from services.orchestrator import CognitiveOrchestrator

    try:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("candle_timeframe", "5m", updated_by="test")
            AppSettingsRepository(session).set("candle_lookback", "42", updated_by="test")

        orch = CognitiveOrchestrator()
        proposal = orch.propose("BTCUSDT")
        assert proposal is not None
        assert proposal["ctx"].market.timeframe == "5m"
        assert len(proposal["data"]) <= 42
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "candle_timeframe", DEFAULTS["candle_timeframe"], updated_by="test",
            )
            AppSettingsRepository(session).set(
                "candle_lookback", DEFAULTS["candle_lookback"], updated_by="test",
            )
