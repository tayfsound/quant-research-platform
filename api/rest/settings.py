"""Faz 188: kullanıcının kendi risk/mod ayarlarını gerçekten kontrol
edebilmesi için API — bkz. database/repositories/app_settings_repository.py."""
from fastapi import APIRouter, Depends, HTTPException

from contracts.auth import Role
from database.repositories.app_settings_repository import (
    DEFAULTS,
    TRADE_HORIZON_SECONDS,
    AppSettingsRepository,
)
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user, require_role

router = APIRouter(prefix="/settings", tags=["settings"])


def _validate(key: str, value: str) -> None:
    if key == "trading_mode":
        if value not in ("test", "live"):
            raise HTTPException(400, "trading_mode must be 'test' or 'live'")
    elif key == "max_concurrent_positions":
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "max_concurrent_positions must be a positive integer")
    elif key == "max_capital_pct":
        try:
            v = float(value)
            if not (0 < v <= 1):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "max_capital_pct must be a number in (0, 1]")
    elif key == "starting_capital":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "starting_capital must be a positive number")
    elif key == "trade_horizon":
        if value not in TRADE_HORIZON_SECONDS:
            raise HTTPException(400, f"trade_horizon must be one of {list(TRADE_HORIZON_SECONDS)}")
    else:
        raise HTTPException(400, f"unknown setting key: {key}")


@router.get("/")
async def get_settings_(user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        return {"settings": AppSettingsRepository(session).get_all()}


@router.post("/{key}")
async def set_setting(key: str, value: str, user: AuthContext = Depends(require_role(Role.ADMIN))):
    _validate(key, value)
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(key, value, updated_by=user.username)
        return {"key": key, "value": value, "updated_by": user.username}


@router.get("/defaults")
async def get_defaults(user: AuthContext = Depends(get_current_user)):
    return {"defaults": DEFAULTS, "trade_horizon_seconds": TRADE_HORIZON_SECONDS}
