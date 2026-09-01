"""Online Feature Selection (Information Coefficient) API.

analytics/feature_ic.py::compute_feature_ic gerçek zamanlı çağrılır —
deneyler API'sindeki (Faz 250) desenle AYNI: hiçbir şey önceden
hesaplanıp saklanmaz, her istek gerçek kapanmış işlem geçmişinden
taze hesaplanır."""
from fastapi import APIRouter, Depends

from analytics.evaluation_cohort import describe_evaluation_window
from analytics.feature_ic import compute_feature_ic
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/feature-ic", tags=["feature-ic"])


@router.get("/")
def feature_ic(min_sample_size: int = 20, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=100_000)
    return {
        "features": compute_feature_ic(closed_trades, min_sample_size=min_sample_size),
        "evaluation_window": describe_evaluation_window(closed_trades, limit=100_000),
    }


@router.get("/reports")
def feature_ic_reports(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Faz 268-sonrası — kullanıcı isteği: "Feature IC'yi karar hattına
    bağlama." Yukarıdaki / (canlı, her istekte taze hesaplanır) her zaman
    O ANKİ durumu gösterir — "zamanla nasıl değişti" sorusu bu geçmiş
    olmadan cevaplanamaz. services/tasks.py::refresh_feature_ic_report_
    task'ın haftalık kaydettiği anlık görüntüler (bkz.
    database/repositories/feature_ic_report_repository.py)."""
    from database.repositories.feature_ic_report_repository import FeatureICReportRepository

    with SessionFactory.get_session() as session:
        reports = FeatureICReportRepository(session).get_recent(limit=limit)
    return {"reports": reports}
