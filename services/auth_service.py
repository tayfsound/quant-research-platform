"""Sprint 22-24: password hashing, JWT issuance, API key generation, and the
FastAPI dependencies that resolve a request to a User + enforce role checks
+ record every authorization decision to audit_log.

Fail-closed throughout: a missing/invalid/expired token is 401, an
insufficient role is 403, and an empty SECRET_KEY refuses to issue or verify
tokens at all rather than silently signing with an empty string.
"""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from config import get_settings
from contracts.auth import AuditLogEntry, Role, User
from database.repositories.auth_repository import APIKeyRepository, AuditLogRepository, UserRepository
from database.session_factory import SessionFactory


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _require_secret_key() -> str:
    secret = get_settings().SECRET_KEY
    if not secret:
        # Fail closed: an empty signing key would make every token
        # forgeable (or, worse, every empty-signature token "valid").
        raise RuntimeError("SECRET_KEY is not set — cannot issue or verify auth tokens")
    return secret


def create_access_token(user_id, role: Role) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "role": role.name,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _require_secret_key(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _require_secret_key(), algorithms=[get_settings().JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, key_hash). Only key_hash is ever persisted — the
    raw key is shown to the caller exactly once, at creation, same
    principle as a password."""
    raw_key = "qrp_" + secrets.token_urlsafe(32)
    return raw_key, hash_api_key(raw_key)


def hash_api_key(raw_key: str) -> str:
    # SHA256, not bcrypt: API keys are already high-entropy random tokens
    # (not human-chosen passwords), so a fast deterministic hash that
    # supports direct lookup-by-hash is the right tool here, not a slow
    # per-guess password hash.
    return hashlib.sha256(raw_key.encode()).hexdigest()


class AuthContext(User):
    """A resolved, authenticated caller — same shape as User plus nothing
    extra, kept as a distinct name so endpoint signatures read clearly."""
    pass


def _record_audit(session, *, user_id, username, action: str, resource: str, allowed: bool, detail: str = ""):
    AuditLogRepository(session).record(
        AuditLogEntry(
            user_id=user_id, username=username, action=action, resource=resource,
            allowed=allowed, detail=detail,
        )
    )


async def get_current_user(request: Request) -> AuthContext:
    """Resolves either a Bearer JWT or an X-API-Key header to a user.
    Every call — success or failure — is written to audit_log."""
    resource = request.url.path
    action = request.method

    with SessionFactory.get_session() as session:
        auth_header = request.headers.get("authorization", "")
        api_key_header = request.headers.get("x-api-key", "")

        user_row = None
        detail = ""

        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]
            payload = decode_access_token(token)
            if payload is not None:
                user_row = UserRepository(session).get_by_id(payload["sub"])
            else:
                detail = "invalid_or_expired_token"
        elif api_key_header:
            key_row = APIKeyRepository(session).get_by_hash(hash_api_key(api_key_header))
            if key_row is not None:
                user_row = UserRepository(session).get_by_id(key_row.user_id)
            else:
                detail = "invalid_or_revoked_api_key"
        else:
            detail = "missing_credentials"

        if user_row is None or user_row.disabled:
            if user_row is not None and user_row.disabled:
                detail = "user_disabled"
            _record_audit(
                session, user_id=None, username=None, action=action,
                resource=resource, allowed=False, detail=detail or "user_not_found",
            )
            raise HTTPException(status_code=401, detail="unauthorized")

        _record_audit(
            session, user_id=user_row.id, username=user_row.username, action=action,
            resource=resource, allowed=True,
        )

        return AuthContext(
            id=user_row.id,
            username=user_row.username,
            password_hash=user_row.password_hash,
            role=Role.from_str(user_row.role),
            created_at=user_row.created_at,
            disabled=user_row.disabled,
        )


def require_role(min_role: Role):
    """Dependency factory: raises 403 (and audits the denial) if the caller's
    role is below min_role. AI/learning code cannot call this to grant
    itself access — it's a request-scoped FastAPI dependency, only reachable
    through an actual HTTP call with real credentials."""

    async def _check(request: Request, user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.role < min_role:
            with SessionFactory.get_session() as session:
                _record_audit(
                    session, user_id=user.id, username=user.username,
                    action=f"{request.method}:role_check", resource=request.url.path,
                    allowed=False, detail=f"requires {min_role.name}, has {user.role.name}",
                )
            raise HTTPException(status_code=403, detail="insufficient_role")
        return user

    return _check
