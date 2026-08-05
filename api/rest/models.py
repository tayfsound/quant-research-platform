"""Model REST endpoint'leri."""
from uuid import UUID

from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/models", tags=["models"])

@router.get("/{model_id}/predictions")
async def get_predictions(
    model_id: UUID,
    symbol: str = "BTCUSDT",
    from_dt: str = "",
    to_dt: str = "",
    user: AuthContext = Depends(get_current_user),
):
    return {
        "model_id": model_id,
        "predictions": [
            {"timestamp": "2026-07-20T00:00:00Z", "direction": 1, "confidence": 0.82},
        ]
    }
