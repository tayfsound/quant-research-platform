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


def test_admin_can_set_max_open_positions_per_symbol_direction():
    """Faz 268-sonrası — kullanıcı isteği: bu ayar (gerçek olaydan sonra
    eklendi — 54 XAUTUSDT SHORT aynı anda açık bulunmuştu) önceden Settings
    sayfasında hiç yoktu, sadece koddaki varsayılana (5) sabitliydi."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/max_open_positions_per_symbol_direction",
            params={"value": "3"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 200

        with SessionFactory.get_session() as session:
            assert AppSettingsRepository(session).get("max_open_positions_per_symbol_direction") == "3"


def test_max_open_positions_per_symbol_direction_rejects_non_positive_value():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post(
            "/api/v1/settings/max_open_positions_per_symbol_direction",
            params={"value": "0"},
            headers=make_authed_headers(Role.ADMIN),
        )
        assert response.status_code == 400


def test_multi_timeframe_cascade_settings_accept_valid_and_reject_invalid_values():
    """Faz 268-sonrası — kullanıcı isteği: her işlemden önce en az 15dk/
    4h/1g'nin AYRI AYRI değerlendirilmesi. Mekanizma (services/
    orchestrator.py::propose()) zaten vardı ama Settings API'sinde hiç
    doğrulanmıyordu — kullanıcı bunu API'den hiç değiştiremezdi."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            ok = client.post(
                "/api/v1/settings/multi_timeframe_cascade_enabled",
                params={"value": "true"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok.status_code == 200
            with SessionFactory.get_session() as session:
                assert AppSettingsRepository(session).get("multi_timeframe_cascade_enabled") == "true"

            bad = client.post(
                "/api/v1/settings/multi_timeframe_cascade_enabled",
                params={"value": "yolo"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad.status_code == 400

            ok_tf = client.post(
                "/api/v1/settings/multi_timeframe_cascade_timeframes",
                params={"value": "15m,4h"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok_tf.status_code == 200
            with SessionFactory.get_session() as session:
                assert AppSettingsRepository(session).get("multi_timeframe_cascade_timeframes") == "15m,4h"

            bad_tf = client.post(
                "/api/v1/settings/multi_timeframe_cascade_timeframes",
                params={"value": "15m,3w"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_tf.status_code == 400

            empty_tf = client.post(
                "/api/v1/settings/multi_timeframe_cascade_timeframes",
                params={"value": ""},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert empty_tf.status_code == 400
        finally:
            with SessionFactory.get_session() as session:
                repo = AppSettingsRepository(session)
                repo.set("multi_timeframe_cascade_enabled", DEFAULTS["multi_timeframe_cascade_enabled"], updated_by="test")
                repo.set("multi_timeframe_cascade_timeframes", DEFAULTS["multi_timeframe_cascade_timeframes"], updated_by="test")


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


def test_medium_term_settings_accept_valid_and_reject_invalid_values():
    """Faz 259: orta-vadeli pozisyon katmanının ayarları — kısa-vadeliden
    ayrı sermaye yüzdesi/zaman dilimi/eşzamanlı pozisyon sayısı."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            ok = client.post(
                "/api/v1/settings/medium_term_enabled",
                params={"value": "true"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok.status_code == 200

            ok2 = client.post(
                "/api/v1/settings/medium_term_timeframe",
                params={"value": "4h"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok2.status_code == 200

            bad_tf = client.post(
                "/api/v1/settings/medium_term_timeframe",
                params={"value": "1m"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_tf.status_code == 400

            bad_pct = client.post(
                "/api/v1/settings/medium_term_capital_pct",
                params={"value": "1.5"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_pct.status_code == 400

            bad_concurrent = client.post(
                "/api/v1/settings/medium_term_max_concurrent",
                params={"value": "0"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_concurrent.status_code == 400
        finally:
            with SessionFactory.get_session() as session:
                repo = AppSettingsRepository(session)
                for key in ("medium_term_enabled", "medium_term_timeframe"):
                    repo.set(key, DEFAULTS[key], updated_by="test")


def test_pump_fade_settings_accept_valid_and_reject_invalid_values():
    """Faz 268-sonrası — kullanıcı bulgusu: pump-fade ayarları DB
    DEFAULTS'a eklenmişti ama Settings API'nin _validate() beyaz
    listesine hiç eklenmemişti — POST her zaman 400 "unknown setting
    key" dönüyordu, kullanıcı bu modülü açık uçtan hiç açamıyordu."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            ok = client.post(
                "/api/v1/settings/pump_fade_enabled",
                params={"value": "true"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok.status_code == 200

            bad_enabled = client.post(
                "/api/v1/settings/pump_fade_enabled",
                params={"value": "yes"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_enabled.status_code == 400

            ok_pct = client.post(
                "/api/v1/settings/pump_fade_capital_pct",
                params={"value": "0.1"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok_pct.status_code == 200

            bad_pct = client.post(
                "/api/v1/settings/pump_fade_capital_pct",
                params={"value": "1.5"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_pct.status_code == 400

            ok_leverage = client.post(
                "/api/v1/settings/pump_fade_leverage",
                params={"value": "10"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok_leverage.status_code == 200

            bad_leverage = client.post(
                "/api/v1/settings/pump_fade_leverage",
                params={"value": "200"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_leverage.status_code == 400

            bad_gain = client.post(
                "/api/v1/settings/pump_fade_min_gain_pct",
                params={"value": "0"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_gain.status_code == 400

            bad_lookback = client.post(
                "/api/v1/settings/pump_fade_lookback_hours",
                params={"value": "0"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_lookback.status_code == 400

            bad_stop = client.post(
                "/api/v1/settings/pump_fade_stop_distance_pct",
                params={"value": "1"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad_stop.status_code == 400
        finally:
            with SessionFactory.get_session() as session:
                repo = AppSettingsRepository(session)
                for key in ("pump_fade_enabled", "pump_fade_capital_pct", "pump_fade_leverage"):
                    repo.set(key, DEFAULTS[key], updated_by="test")


def test_pairs_trading_leg_capital_usd_accepts_valid_and_rejects_invalid_values():
    """Faz 268-sonrası — eski LEG_SIZE=0.2 sabit ham birim yerine dolar
    bazlı, kullanıcı ayarlanabilir bir bacak boyutu."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        try:
            ok = client.post(
                "/api/v1/settings/pairs_trading_leg_capital_usd",
                params={"value": "250"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert ok.status_code == 200

            bad = client.post(
                "/api/v1/settings/pairs_trading_leg_capital_usd",
                params={"value": "0"},
                headers=make_authed_headers(Role.ADMIN),
            )
            assert bad.status_code == 400
        finally:
            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "pairs_trading_leg_capital_usd", DEFAULTS["pairs_trading_leg_capital_usd"], updated_by="test"
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
