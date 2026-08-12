"""Online Feature Selection (Information Coefficient) API.

analytics/feature_ic.py::compute_feature_ic gerçek zamanlı çağrılır —
deneyler API'sindeki (Faz 250) desenle AYNI: hiçbir şey önceden
hesaplanıp saklanmaz, her istek gerçek kapanmış işlem geçmişinden
taze hesaplanır."""
from fastapi import APIRouter, Depends

from analytics.feature_ic import compute_feature_ic
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/feature-ic", tags=["feature-ic"])


@router.get("/")
async def feature_ic(min_sample_size: int = 20, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=100_000)
    return {"features": compute_feature_ic(closed_trades, min_sample_size=min_sample_size)}
