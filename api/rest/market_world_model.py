"""Market World Model API — Cognitive Core 5.0-6.0 (Faz 901-940).

Kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte canlıya alındı.
services/market_world_model_gatherer.py::gather_market_world_model()
gerçek zamanlı çağrılır — MAE/MFE Confidence API'sindeki desenle AYNI."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.market_world_model_gatherer import gather_market_world_model

router = APIRouter(prefix="/market-world-model", tags=["market-world-model"])


@router.get("/")
def market_world_model(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_market_world_model()}


@router.get("/reports")
def market_world_model_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.market_world_model_report_repository import (
        MarketWorldModelReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = MarketWorldModelReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
