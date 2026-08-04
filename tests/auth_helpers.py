"""Shared test helper: create a user with a specific role and a matching
bearer token, bypassing the API's first-user-is-admin bootstrap (which is
order-dependent across a shared test DB — direct repository creation is
deterministic regardless of test execution order)."""
from uuid import uuid4

from contracts.auth import Role, User
from database.repositories.auth_repository import UserRepository
from database.session_factory import SessionFactory
from services.auth_service import create_access_token, hash_password


def make_authed_headers(role: Role = Role.ADMIN) -> dict[str, str]:
    username = f"test_{role.name.lower()}_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        user = User(username=username, password_hash=hash_password("irrelevant-pw-123"), role=role)
        UserRepository(session).create(user)

    token = create_access_token(user.id, role)
    return {"Authorization": f"Bearer {token}"}
