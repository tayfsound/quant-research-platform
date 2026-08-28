"""Feature Relationship (redundancy matrix + koşullu IC) API — Faz 368.

analytics/feature_relationship.py gerçek zamanlı çağrılır — api/rest/
feature_ic.py'deki desenle AYNI: hiçbir şey önceden hesaplanıp saklanmaz,
her istek gerçek kapanmış işlem geçmişinden taze hesaplanır."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.feature_relationship_gatherer import gather_feature_relationship

router = APIRouter(prefix="/feature-relationship", tags=["feature-relationship"])


@router.get("/")
def feature_relationship(user: AuthContext = Depends(get_current_user)):
    return gather_feature_relationship()


@router.get("/reports")
def feature_relationship_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """feature-ic/reports ile AYNI desen: yukarıdaki / her zaman O ANKİ
    durumu gösterir, bu endpoint services/tasks.py::refresh_feature_
    relationship_report_task'ın haftalık kaydettiği anlık görüntüleri
    döner (bkz. database/repositories/feature_relationship_report_
    repository.py)."""
    from database.repositories.feature_relationship_report_repository import (
        FeatureRelationshipReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        reports = FeatureRelationshipReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
