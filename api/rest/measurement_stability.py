"""Measurement Stability API — Faz 415. research-summary ile AYNI desen
(canlı, buton-tetiklemeli — bazı alt modüller tüm watchlist'i tarıyor)."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.measurement_stability_summary_gatherer import gather_measurement_stability_summary

router = APIRouter(prefix="/measurement-stability", tags=["measurement-stability"])


@router.get("/")
def measurement_stability(user: AuthContext = Depends(get_current_user)):
    return gather_measurement_stability_summary()
