"""Model Drift Detection (PSI/KS-test) API.

analytics/model_drift.py::compute_feature_drift gerçek zamanlı çağrılır —
feature-ic/deneyler API'leriyle AYNI desen: hiçbir şey önceden hesaplanıp
saklanmaz, her istek gerçek karar geçmişinden taze hesaplanır."""
from fastapi import APIRouter, Depends

from analytics.model_drift import compute_feature_drift
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/model-drift", tags=["model-drift"])


@router.get("/")
def model_drift(
    limit: int = 2000, split_frac: float = 0.5, user: AuthContext = Depends(get_current_user)
):
    with SessionFactory.get_session() as session:
        decisions = DecisionPersistor(session).list_recent(limit=limit)
    return {"features": compute_feature_drift(decisions, split_frac=split_frac)}
