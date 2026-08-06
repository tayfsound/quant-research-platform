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


def test_trade_horizon_shorter_than_twice_the_candle_timeframe_is_rejected():
    """Faz 224 review bulgusu (B): trade_horizon ve candle_timeframe
    bağımsız ayarlar — kullanıcı Settings'ten ikisini de ayrı ayrı
    değiştirip Faz 215'teki gerçek bug'a (pozisyon, sinyalin üretildiği
    mum bile tamamlanmadan kapanıyordu) tekrar düşebilirdi. candle_
    timeframe varsayılan "15m" (900s) iken trade_horizon="short" (600s)
    -> 600 < 900*2, reddedilmeli."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "candle_timeframe", DEFAULTS["candle_timeframe"], updated_by="test"
            )
        response = client.post(
            "/api/v1/settings/trade_horizon",
            params={"value": "short"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400
        assert "candle_timeframe" in response.json()["detail"]


def test_candle_timeframe_longer_than_half_the_trade_horizon_is_rejected():
    """Ters yön: trade_horizon varsayılan "medium" (14400s) iken
    candle_timeframe="1d" (86400s) -> 14400 < 86400*2, reddedilmeli."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "trade_horizon", DEFAULTS["trade_horizon"], updated_by="test"
                )
            response = client.post(
                "/api/v1/settings/candle_timeframe",
                params={"value": "1d"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert response.status_code == 400
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "candle_timeframe", DEFAULTS["candle_timeframe"], updated_by="test"
                )


def test_consistent_horizon_and_timeframe_combination_is_accepted():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "trade_horizon", DEFAULTS["trade_horizon"], updated_by="test"
                )
            # medium (14400s) >= 1h (3600s) * 2 -> tutarlı, kabul edilmeli.
            response = client.post(
                "/api/v1/settings/candle_timeframe",
                params={"value": "1h"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert response.status_code == 200
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "candle_timeframe", DEFAULTS["candle_timeframe"], updated_by="test"
                )


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
            # Faz 224 review (B): candle_timeframe artık trade_horizon'a
            # göre çapraz doğrulanıyor — "4h" (14400s) için trade_horizon
            # en az 28800s olmalı, bu yüzden burada açıkça "long" (86400s)
            # set ediliyor (varsayılan "medium"=14400s "4h" ile TAM sınırda
            # kalıyor, testin diğer testlerin bıraktığı state'e bağımlı
            # olmaması için "long" daha güvenli).
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("trade_horizon", "long", updated_by="test")
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
                AppSettingsRepository(session).set(
                    "trade_horizon", DEFAULTS["trade_horizon"], updated_by="test",
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
