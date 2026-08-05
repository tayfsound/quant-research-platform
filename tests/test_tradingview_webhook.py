"""Faz 185: TradingView doesn't work like Binance (no API key + bulk pull) —
Pine Script alerts POST to a webhook URL we control. This proves the real
receiver end to end: a real HTTP POST persists to external_signals, wrong
secret is rejected when one is configured, and the (auth-protected, this
platform's own users only) read-back endpoint lists it."""
from unittest.mock import patch
from uuid import uuid4

from config import Settings
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_webhook_persists_a_real_signal_and_is_listed_back():
    symbol = f"TVTEST{uuid4().hex[:6]}"
    resp = _client().post("/api/v1/webhooks/tradingview", json={
        "symbol": symbol, "signal": "LONG", "rsi": 28, "ema_cross": "bullish", "volume_ratio": 2.4,
    })
    assert resp.status_code == 200
    assert resp.json()["symbol"] == symbol

    listing = _client().get(
        f"/api/v1/webhooks/tradingview/recent?symbol={symbol}",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert listing.status_code == 200
    signals = listing.json()["signals"]
    assert len(signals) == 1
    assert signals[0]["signal"] == "LONG"
    assert signals[0]["payload"]["rsi"] == 28
    # The shared secret (if any) must never be stored/echoed back.
    assert "secret" not in signals[0]["payload"]


def test_webhook_rejects_wrong_secret_when_configured():
    with patch("api.rest.webhooks.get_settings", return_value=Settings(TRADINGVIEW_WEBHOOK_SECRET="realsecret")):
        resp = _client().post("/api/v1/webhooks/tradingview", json={
            "symbol": "BTCUSDT", "signal": "LONG", "secret": "wrong",
        })
    assert resp.status_code == 403


def test_webhook_accepts_correct_secret_when_configured():
    symbol = f"TVSEC{uuid4().hex[:6]}"
    with patch("api.rest.webhooks.get_settings", return_value=Settings(TRADINGVIEW_WEBHOOK_SECRET="realsecret")):
        resp = _client().post("/api/v1/webhooks/tradingview", json={
            "symbol": symbol, "signal": "SHORT", "secret": "realsecret",
        })
    assert resp.status_code == 200


def test_webhook_requires_symbol():
    resp = _client().post("/api/v1/webhooks/tradingview", json={"signal": "LONG"})
    assert resp.status_code == 400


def test_recent_signals_endpoint_requires_auth():
    resp = _client().get("/api/v1/webhooks/tradingview/recent")
    assert resp.status_code in (401, 403)
