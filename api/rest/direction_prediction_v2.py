"""Direction Prediction v2 (Brier Score) API — Cognitive Core 2.0 / M4 (Faz 519-543).

Kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte canlıya alındı.
services/direction_prediction_v2_gatherer.py::gather_direction_prediction_v2()
gerçek zamanlı çağrılır — MAE/MFE Confidence API'sindeki desenle AYNI."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.direction_prediction_v2_gatherer import gather_direction_prediction_v2

router = APIRouter(prefix="/direction-prediction-v2", tags=["direction-prediction-v2"])


@router.get("/")
def direction_prediction_v2(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_direction_prediction_v2()}


@router.get("/reports")
def direction_prediction_v2_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.direction_prediction_v2_report_repository import (
        DirectionPredictionV2ReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = DirectionPredictionV2ReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
