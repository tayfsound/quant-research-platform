"""Research Summary API — Faz 326. Kullanıcı isteği: 10 Grup B (ölçüm-
only) araştırma modülünü tek tek dolaşmak yerine tek bir düğmeyle
hepsinin özetini görebilmek."""
from fastapi import APIRouter, Depends

from services.auth_service import AuthContext, get_current_user
from services.research_summary_gatherer import gather_research_summary

router = APIRouter(prefix="/research-summary", tags=["research-summary"])


@router.get("/")
def research_summary(user: AuthContext = Depends(get_current_user)):
    return gather_research_summary()
