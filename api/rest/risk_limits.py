"""Risk Limit API — gap #15: ctx.risk.limits'i üretimde gerçekten dolduran
tek gerçek kaynak. Faz 160'ın "insan onayı zorunluluğu" ilkesiyle tutarlı:
yeni bir limit set etmek ADMIN rolü gerektirir (weight_approval/plugin trust
ile aynı desen — kimliği doğrulanmış bir insanın eylemi, ayrı bir approve
adımı değil, çünkü zaten sadece ADMIN bunu yapabiliyor)."""
from datetime import datetime, UTC
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, Depends

from config import get_settings
from contracts.auth import Role
from database.repositories.risk_limit_repository import RiskLimitModel, RiskLimitRepository
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user, require_role

router = APIRouter(prefix="/risk-limits", tags=["risk-limits"])


@router.post("/{limit_type}")
def set_risk_limit(
    limit_type: str,
    value: float,
    scope: str = "global",
    user: AuthContext = Depends(require_role(Role.ADMIN)),
):
    secret = get_settings().SECRET_KEY
    # RiskLimitEntry.verify() convention: empty hash = dev mode, always
    # passes. Only sign for real once a real SECRET_KEY is configured —
    # signing with an empty secret would produce a hash that "verifies"
    # trivially anyway, so there's no security lost by being explicit here.
    limit_hash = sha256(f"{value}:{secret}".encode()).hexdigest() if secret else ""

    row = RiskLimitModel(
        id=uuid4(),
        scope=scope,
        limit_type=limit_type,
        value=value,
        hash=limit_hash,
        created_by=user.username,
        created_at=datetime.now(UTC),
    )
    row_id = row.id
    with SessionFactory.get_session() as session:
        RiskLimitRepository(session).save(row)

    return {
        "id": str(row_id),
        "scope": scope,
        "limit_type": limit_type,
        "value": value,
        "created_by": user.username,
    }


@router.get("/")
def list_risk_limits(scope: str = "global", user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        rows = RiskLimitRepository(session).list_active(scope=scope)
        return {
            "scope": scope,
            "limits": [
                {
                    "limit_type": r.limit_type,
                    "value": r.value,
                    "created_by": r.created_by,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }
