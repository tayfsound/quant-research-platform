"""Strategy × Regime Compatibility API — Faz 338 (MetaStrategyAgent v1).

Kullanıcı onayı: "Bu stratejinin şu anki piyasa rejiminde gerçek edge'i
var mı?" sorusuna GERÇEK verilerle cevap veren, ölçüm-only bir modül —
Self-Model/Causal Inference API'sindeki desenle AYNI: hiçbir şey önceden
hesaplanıp saklanmaz, her istek gerçek kapanmış kararlardan taze
hesaplanır. v1'de HİÇBİR gate'e bağlanmıyor, sadece rapor."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.strategy_regime_compatibility_gatherer import gather_strategy_regime_compatibility

router = APIRouter(prefix="/strategy-regime-compatibility", tags=["strategy-regime-compatibility"])


@router.get("/")
def strategy_regime_compatibility(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_strategy_regime_compatibility()}
