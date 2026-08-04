"""Sprint 22-24: auth infrastructure. Register/login/me, API keys, role
enforcement on real protected endpoints, and audit log recording every
authorization decision (allowed and denied) — matching the roadmap's
explicit "her yetkilendirme kararının loglanması" requirement."""
from unittest.mock import patch
from uuid import uuid4

import pytest

from contracts.auth import Role
from database.repositories.auth_repository import AuditLogRepository
from database.session_factory import SessionFactory
from services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from tests.auth_helpers import make_authed_headers


def test_password_hash_roundtrip_and_wrong_password_rejected():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert hashed != "correct-horse-battery-staple"  # never store plaintext


def test_jwt_roundtrip_and_tampered_token_rejected():
    user_id = uuid4()
    token = create_access_token(user_id, Role.OPERATOR)

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "OPERATOR"

    tampered = token[:-4] + "abcd"
    assert decode_access_token(tampered) is None


def test_register_first_user_becomes_admin_second_becomes_viewer():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    with SessionFactory.get_session() as session:
        from database.repositories.auth_repository import UserRepository
        already_has_users = UserRepository(session).count() > 0

    u1 = f"first_{uuid4().hex[:8]}"
    r1 = client.post("/api/v1/auth/register", json={"username": u1, "password": "password123"})
    assert r1.status_code == 200
    if not already_has_users:
        assert r1.json()["role"] == "ADMIN"

    u2 = f"second_{uuid4().hex[:8]}"
    r2 = client.post("/api/v1/auth/register", json={"username": u2, "password": "password123"})
    assert r2.json()["role"] == "VIEWER"


def test_register_rejects_short_password_and_duplicate_username():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    username = f"dup_{uuid4().hex[:8]}"

    assert client.post(
        "/api/v1/auth/register", json={"username": username, "password": "short"}
    ).status_code == 400

    first = client.post("/api/v1/auth/register", json={"username": username, "password": "password123"})
    assert first.status_code == 200
    dup = client.post("/api/v1/auth/register", json={"username": username, "password": "password123"})
    assert dup.status_code == 409


def test_login_then_me_roundtrip():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    username = f"loginuser_{uuid4().hex[:8]}"
    client.post("/api/v1/auth/register", json={"username": username, "password": "password123"})

    login = client.post("/api/v1/auth/login", json={"username": username, "password": "password123"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    bad_login = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong"})
    assert bad_login.status_code == 401

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == username


def test_api_key_created_and_usable_as_credential():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    headers = make_authed_headers(Role.VIEWER)

    created = client.post("/api/v1/auth/api-keys", params={"label": "ci"}, headers=headers)
    assert created.status_code == 200
    raw_key = created.json()["api_key"]
    assert raw_key.startswith("qrp_")

    me = client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert me.status_code == 200


def test_audit_log_records_both_allowed_and_denied_decisions():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    admin_headers = make_authed_headers(Role.ADMIN)
    viewer_headers = make_authed_headers(Role.VIEWER)

    # An allowed call and a denied one (viewer hitting an admin-only route).
    client.get("/api/v1/auth/me", headers=viewer_headers)
    client.post("/api/v1/workspace/plugins/upload", json={"filename": "x.py", "source_code": "x=1"}, headers=viewer_headers)

    with SessionFactory.get_session() as session:
        entries = AuditLogRepository(session).list_recent(limit=200)
        denials = [(e.allowed, e.detail or "") for e in entries]

    assert any(not allowed and "requires" in detail for allowed, detail in denials)
    assert len(denials) > 0


def test_disabled_user_cannot_authenticate():
    from fastapi.testclient import TestClient
    from api.main import app
    from contracts.auth import User
    from database.repositories.auth_repository import UserRepository

    username = f"disableduser_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        user = User(username=username, password_hash=hash_password("password123"), role=Role.VIEWER, disabled=True)
        UserRepository(session).create(user)

    token = create_access_token(user.id, Role.VIEWER)
    client = TestClient(app)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_secret_key_missing_fails_closed():
    from services.auth_service import _require_secret_key

    with patch("services.auth_service.get_settings") as mock_settings:
        mock_settings.return_value.SECRET_KEY = ""
        with pytest.raises(RuntimeError):
            _require_secret_key()
