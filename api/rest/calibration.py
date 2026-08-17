"""Probability Calibration (ECE) API — Cognitive Core 2.0 / M4.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — ECE ilk aday. analytics/
calibration_uncertainty.py::compute_expected_calibration_error()
gerçek zamanlı çağrılır — Feature IC API'sindeki (Faz 268-sonrası)
desenle AYNI: hiçbir şey önceden hesaplanıp saklanmaz, her istek gerçek
kapanmış işlem geçmişinden taze hesaplanır."""
from fastapi import APIRouter, Depends

from analytics.calibration_uncertainty import (
    compute_expected_calibration_error,
    extract_predictions_from_closed_trades,
)
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("/")
async def calibration(user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=100_000)
    predictions = extract_predictions_from_closed_trades(closed_trades)
    return {"result": compute_expected_calibration_error(predictions), "total_closed_trades": len(closed_trades)}


@router.get("/reports")
async def calibration_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Yukarıdaki / (canlı, her istekte taze hesaplanır) her zaman O ANKİ
    durumu gösterir — "kalibrasyon zamanla nasıl değişti" sorusu bu geçmiş
    olmadan cevaplanamaz. services/tasks.py::refresh_calibration_report_
    task'ın haftalık kaydettiği anlık görüntüler."""
    from database.repositories.calibration_report_repository import CalibrationReportRepository

    with SessionFactory.get_session() as session:
        reports = CalibrationReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
