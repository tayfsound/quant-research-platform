"""Auth API — Sprint 22-24."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import get_settings
from contracts.auth import Role, User
from database.repositories.auth_repository import APIKeyRepository, AuditLogRepository, UserRepository
from database.session_factory import SessionFactory
from services.auth_service import (
    AuthContext,
    create_access_token,
    generate_api_key,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    setup_token: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(req: RegisterRequest):
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")

    with SessionFactory.get_session() as session:
        repo = UserRepository(session)
        if repo.get_by_username(req.username) is not None:
            raise HTTPException(status_code=409, detail="username_taken")

        # Bootstrap: the very first user becomes ADMIN (there is no other
        # authenticated actor yet to grant that role); every user after
        # that defaults to VIEWER and must be promoted by an admin.
        is_bootstrap = repo.count() == 0
        if is_bootstrap:
            setup_token = get_settings().ADMIN_SETUP_TOKEN
            # Security review finding (confidence 5/10): with no setup
            # token configured, anyone who registers first becomes ADMIN —
            # fine for local dev (the empty-token default, same convention
            # as SECRET_KEY/RiskLimitEntry elsewhere), but a real deployment
            # should set ADMIN_SETUP_TOKEN so bootstrap admin can't be raced.
            if setup_token and req.setup_token != setup_token:
                raise HTTPException(status_code=403, detail="invalid_setup_token")

        role = Role.ADMIN if is_bootstrap else Role.VIEWER

        user = User(username=req.username, password_hash=hash_password(req.password), role=role)
        repo.create(user)
        return {"id": str(user.id), "username": user.username, "role": user.role.name}


@router.post("/login")
async def login(req: LoginRequest):
    with SessionFactory.get_session() as session:
        row = UserRepository(session).get_by_username(req.username)
        if row is None or row.disabled or not verify_password(req.password, row.password_hash):
            raise HTTPException(status_code=401, detail="invalid_credentials")

        token = create_access_token(row.id, Role.from_str(row.role))
        return {"access_token": token, "token_type": "bearer", "role": row.role}


@router.get("/me")
async def me(user: AuthContext = Depends(get_current_user)):
    return {"id": str(user.id), "username": user.username, "role": user.role.name}


@router.post("/api-keys")
async def create_api_key(label: str = "", user: AuthContext = Depends(get_current_user)):
    from contracts.auth import APIKey

    raw_key, key_hash = generate_api_key()
    with SessionFactory.get_session() as session:
        APIKeyRepository(session).create(APIKey(user_id=user.id, key_hash=key_hash, label=label))

    return {"api_key": raw_key, "label": label, "note": "shown once — store it now"}


@router.get("/audit-log")
async def audit_log(limit: int = 100, user: AuthContext = Depends(require_role(Role.ADMIN))):
    with SessionFactory.get_session() as session:
        rows = AuditLogRepository(session).list_recent(limit=limit)
        return {
            "entries": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "username": r.username,
                    "action": r.action,
                    "resource": r.resource,
                    "allowed": r.allowed,
                    "detail": r.detail,
                }
                for r in rows
            ]
        }
