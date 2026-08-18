"""Collective Intelligence (Condorcet'in Jüri Teoremi) API — Cognitive Core 10.0.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — Collective Intelligence,
Causal Inference'tan sonraki Grup B adayı. services/collective_
intelligence_gatherer.py::gather_collective_intelligence() gerçek
zamanlı çağrılır — Calibration/Feature IC/Self-Model/Causal Inference
API'sindeki desenle AYNI."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.collective_intelligence_gatherer import gather_collective_intelligence

router = APIRouter(prefix="/collective-intelligence", tags=["collective-intelligence"])


@router.get("/")
def collective_intelligence(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_collective_intelligence()}


@router.get("/reports")
def collective_intelligence_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Yukarıdaki / (canlı, her istekte taze) her zaman O ANKİ durumu
    gösterir — "council gerçekten tek ajandan daha iyi mi" sorusunun
    zaman içindeki değişimi bu geçmiş olmadan cevaplanamaz. services/
    tasks.py::refresh_collective_intelligence_report_task'ın haftalık
    kaydettiği anlık görüntüler."""
    from database.repositories.collective_intelligence_report_repository import (
        CollectiveIntelligenceReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = CollectiveIntelligenceReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
