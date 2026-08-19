"""Opportunity Quality / Meta-Labeling API — Cognitive Core 2.0 (Faz 569-593).

Kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte canlıya alındı.
services/opportunity_quality_gatherer.py::gather_opportunity_quality()
gerçek zamanlı çağrılır — MAE/MFE Confidence API'sindeki desenle AYNI."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.opportunity_quality_gatherer import gather_opportunity_quality

router = APIRouter(prefix="/opportunity-quality", tags=["opportunity-quality"])


@router.get("/")
def opportunity_quality(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_opportunity_quality()}


@router.get("/reports")
def opportunity_quality_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.opportunity_quality_report_repository import (
        OpportunityQualityReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = OpportunityQualityReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
