"""Feature Registry API — Faz 294 (Cognitive Core 2.0 / M1) Feature
lineage ve veri bilimi çekirdeği. market_data/features/feature_registry.py'nin
elle doğrulanmış katalogunu döner — "bu feature'ı hangi fonksiyon
üretiyor, ne anlama geliyor" sorusuna programatik cevap."""
from dataclasses import asdict

from fastapi import APIRouter, Depends

from market_data.features.feature_registry import FEATURE_REGISTRY
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/feature-registry", tags=["feature-registry"])


@router.get("/")
def feature_registry(user: AuthContext = Depends(get_current_user)):
    return {"features": {name: asdict(spec) for name, spec in FEATURE_REGISTRY.items()}}
