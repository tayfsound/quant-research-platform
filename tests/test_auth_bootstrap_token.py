"""Security review finding (confidence 5/10, RELEASE_NOTES.md/CURRENT_STATE.md):
the very first /auth/register call always became ADMIN with no way to gate
who gets there first — a real deployment race. ADMIN_SETUP_TOKEN closes it
when configured, while staying empty (no-op, current behavior) by default
for local dev — same convention as SECRET_KEY/RiskLimitEntry elsewhere.

The real DB in this test session already has hundreds of users from earlier
test runs, so "is this really the first user ever" isn't reproducible via
real registration order — UserRepository.count() is mocked to force the
bootstrap branch, same technique the auth_helpers.py docstring already
justifies for order-independence."""
from unittest.mock import patch
from uuid import uuid4

from config import Settings


def _client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


def test_bootstrap_register_rejected_without_correct_setup_token_when_configured():
    with patch("database.repositories.auth_repository.UserRepository.count", return_value=0):
        with patch("api.rest.auth.get_settings", return_value=Settings(ADMIN_SETUP_TOKEN="correct-horse")):
            resp = _client().post(
                "/api/v1/auth/register",
                json={"username": f"race_{uuid4().hex[:8]}", "password": "password123", "setup_token": "wrong"},
            )
    assert resp.status_code == 403


def test_bootstrap_register_succeeds_as_admin_with_correct_setup_token():
    with patch("database.repositories.auth_repository.UserRepository.count", return_value=0):
        with patch("api.rest.auth.get_settings", return_value=Settings(ADMIN_SETUP_TOKEN="correct-horse")):
            resp = _client().post(
                "/api/v1/auth/register",
                json={"username": f"legit_{uuid4().hex[:8]}", "password": "password123", "setup_token": "correct-horse"},
            )
    assert resp.status_code == 200
    assert resp.json()["role"] == "ADMIN"


def test_bootstrap_register_unaffected_when_no_setup_token_configured():
    """Default/dev behavior: ADMIN_SETUP_TOKEN="" — unchanged from before."""
    with patch("database.repositories.auth_repository.UserRepository.count", return_value=0):
        with patch("api.rest.auth.get_settings", return_value=Settings(ADMIN_SETUP_TOKEN="")):
            resp = _client().post(
                "/api/v1/auth/register",
                json={"username": f"devmode_{uuid4().hex[:8]}", "password": "password123"},
            )
    assert resp.status_code == 200
    assert resp.json()["role"] == "ADMIN"
