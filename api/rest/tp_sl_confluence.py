"""TP/SL Confluence API — Faz 299-300.

services/tp_sl_confluence_gatherer.py::gather_tp_sl_confluence() gerçek
zamanlı çağrılır — diğer Grup B/gözlem modülleriyle AYNI desen. Bu
modülün "canlı" tarafı (RiskTargetStage'in hedefi sıkılaştırması)
zaten wire edilmiş durumda — bu endpoint SADECE gözlem/izleme."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.tp_sl_confluence_gatherer import gather_tp_sl_confluence

router = APIRouter(prefix="/tp-sl-confluence", tags=["tp-sl-confluence"])


@router.get("/")
def tp_sl_confluence(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_tp_sl_confluence()}


@router.get("/reports")
def tp_sl_confluence_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    from database.repositories.tp_sl_confluence_report_repository import (
        TpSlConfluenceReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = TpSlConfluenceReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
