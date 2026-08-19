"""Meta-Learning Effectiveness API — Cognitive Core 2.0 / M10 (Faz 744-768).

Kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte canlıya alındı.
services/meta_learning_effectiveness_gatherer.py::
gather_meta_learning_effectiveness() gerçek zamanlı çağrılır — MAE/MFE
Confidence API'sindeki desenle AYNI."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.meta_learning_effectiveness_gatherer import gather_meta_learning_effectiveness

router = APIRouter(prefix="/meta-learning-effectiveness", tags=["meta-learning-effectiveness"])


@router.get("/")
def meta_learning_effectiveness(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_meta_learning_effectiveness()}


@router.get("/reports")
def meta_learning_effectiveness_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.meta_learning_effectiveness_report_repository import (
        MetaLearningEffectivenessReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = MetaLearningEffectivenessReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
