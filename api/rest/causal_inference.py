"""Causal Inference (Granger causality) API — Cognitive Core 4.0.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — Causal Inference, self_model'den
sonraki Grup B adayı. services/causal_inference_gatherer.py::gather_
causal_relationships() gerçek zamanlı çağrılır — Calibration/Feature IC/
Self-Model API'sindeki desenle AYNI: hiçbir şey önceden hesaplanıp
saklanmaz, her istek gerçek piyasa verisinden taze hesaplanır."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.causal_inference_gatherer import gather_causal_relationships

router = APIRouter(prefix="/causal-inference", tags=["causal-inference"])


@router.get("/")
def causal_inference(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_causal_relationships()}


@router.get("/reports")
def causal_inference_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Yukarıdaki / (canlı, her istekte taze) her zaman O ANKİ durumu
    gösterir — "BTC/ETH'nin öngörücülüğü zaman içinde nasıl değişti"
    sorusu bu geçmiş olmadan cevaplanamaz. services/tasks.py::refresh_
    causal_inference_report_task'ın haftalık kaydettiği anlık görüntüler."""
    from database.repositories.causal_inference_report_repository import CausalInferenceReportRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = CausalInferenceReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
