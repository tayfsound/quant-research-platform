"""MAE/MFE Bootstrap Güven Aralığı API — Cognitive Core 2.0 (Faz 469-493).

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — Collective Intelligence'tan
sonraki Grup B adayı. services/mae_mfe_confidence_gatherer.py::
gather_mae_mfe_confidence() gerçek zamanlı çağrılır — Self-Model/Causal
Inference/Collective Intelligence API'sindeki desenle AYNI."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.mae_mfe_confidence_gatherer import gather_mae_mfe_confidence

router = APIRouter(prefix="/mae-mfe-confidence", tags=["mae-mfe-confidence"])


@router.get("/")
def mae_mfe_confidence(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_mae_mfe_confidence()}


@router.get("/reports")
def mae_mfe_confidence_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Yukarıdaki / (canlı, her istekte taze) her zaman O ANKİ durumu
    gösterir — güven aralığının örneklem büyüdükçe daralıp daralmadığı
    bu geçmiş olmadan cevaplanamaz. services/tasks.py::
    refresh_mae_mfe_confidence_report_task'ın haftalık kaydettiği anlık
    görüntüler."""
    from database.repositories.mae_mfe_confidence_report_repository import (
        MaeMfeConfidenceReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = MaeMfeConfidenceReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
