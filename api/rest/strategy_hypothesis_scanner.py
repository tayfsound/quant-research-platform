"""Autonomous Strategy Synthesizer v1 "Regime Gate Discovery" API — Faz 346.

Kullanıcı onayı: v1 kapsamı bugün elle yapılan sürecin (SHORT/
bearish_low bulgusu, Faz 342) otomasyonu. Kasıtlı olarak SADECE
ölçüm/aday üretimi — hiçbir aday burada otomatik bir gate'e
BAĞLANMIYOR, tek çıktısı bir rapor. Bir adayı gerçek bir kod
değişikliğine (Faz 342'deki gibi) dönüştürmek HER ZAMAN ayrı, açık
bir insan kararı gerektirir."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.strategy_hypothesis_scanner_gatherer import gather_strategy_hypothesis_candidates

router = APIRouter(prefix="/strategy-hypothesis-scanner", tags=["strategy-hypothesis-scanner"])


@router.get("/")
def strategy_hypothesis_scanner(user: AuthContext = Depends(get_current_user)):
    return {"result": gather_strategy_hypothesis_candidates()}
