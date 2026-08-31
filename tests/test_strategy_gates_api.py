"""Faz 384 — todo listesi madde 4 (2026-08-31, iki ayrı dış raporda
bulundu): api/rest/strategy_gates.py'nin list_pending/list_blocked
endpoint'lerinde hiç auth yoktu (aynı dosyadaki approve/reject zaten
require_role(Role.OPERATOR) ile korunuyordu — sadece okuma endpoint'leri
açıktı). api/rest/weights.py'nin AYNI sınıf hatası zaten test_weight_
approval_e2e.py'de dolaylı yakalanmıştı (401 regresyonu), burada
strategy_gates.py için doğrudan doğrulanıyor."""
from fastapi.testclient import TestClient

from api.main import app
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers

client = TestClient(app)


def test_list_pending_requires_auth():
    r = client.get("/api/v1/strategy-gates/pending")
    assert r.status_code in (401, 403)


def test_list_pending_succeeds_with_valid_auth():
    r = client.get("/api/v1/strategy-gates/pending", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert "pending" in r.json()


def test_list_blocked_requires_auth():
    r = client.get("/api/v1/strategy-gates/blocked")
    assert r.status_code in (401, 403)


def test_list_blocked_succeeds_with_valid_auth():
    r = client.get("/api/v1/strategy-gates/blocked", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert "blocked" in r.json()
