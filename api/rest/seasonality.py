"""Seasonality Detection API.

analytics/seasonality.py gerçek zamanlı çağrılır — feature-ic/model-drift
API'leriyle AYNI desen: hiçbir şey önceden hesaplanıp saklanmaz, her
istek gerçek kapanmış işlem geçmişinden taze hesaplanır."""
from fastapi import APIRouter, Depends

from analytics.evaluation_cohort import describe_evaluation_window
from analytics.seasonality import compute_day_of_week_seasonality, compute_hourly_seasonality
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/seasonality", tags=["seasonality"])


@router.get("/")
def seasonality(limit: int = 5000, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        trades = DecisionPersistor(session).list_closed_trades(limit=limit)
    return {
        "hourly": compute_hourly_seasonality(trades),
        "day_of_week": compute_day_of_week_seasonality(trades),
        "evaluation_window": describe_evaluation_window(trades, limit=limit),
    }
