"""Self-Model (öz-güvenilirlik) API — Cognitive Core 3.0.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — Self-Model, ECE'den sonraki
Grup B adayı. services/self_model_gatherer.py::gather_self_reliability_
snapshot() gerçek zamanlı çağrılır — Calibration/Feature IC API'sindeki
desenle AYNI: hiçbir şey önceden hesaplanıp saklanmaz, her istek gerçek
alt sistemlerden taze hesaplanır."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.self_model_gatherer import gather_self_reliability_snapshot

router = APIRouter(prefix="/self-model", tags=["self-model"])


@router.get("/")
def self_model(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_self_reliability_snapshot()}


@router.get("/reports")
def self_model_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Yukarıdaki / (canlı, her istekte taze) her zaman O ANKİ durumu
    gösterir — "sistem kendi güvenilirliğini zaman içinde nasıl
    değerlendirdi" sorusu bu geçmiş olmadan cevaplanamaz. services/
    tasks.py::refresh_self_model_report_task'ın haftalık kaydettiği
    anlık görüntüler."""
    from database.repositories.self_model_report_repository import SelfModelReportRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = SelfModelReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
