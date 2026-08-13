"""LLM Decision Critic API — Faz 268-sonrası (kullanıcı isteği).

Dashboard'da serbest metin soru/cevap sekmesi için — llm_reasoner.py::
NvidiaDecisionCritic.ask() gerçek NVIDIA NIM API'sini (deepseek-v4-flash)
çağırır. Kasıtlı olarak sadece danışma — hiçbir gerçek karara/pozisyona
bağlı değil."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/llm-critic", tags=["llm-critic"])


class AskRequest(BaseModel):
    message: str


@router.post("/ask")
async def ask(body: AskRequest, user: AuthContext = Depends(get_current_user)):
    from llm_reasoner import NvidiaDecisionCritic

    critic = NvidiaDecisionCritic()
    response = await critic.ask(body.message)
    return {"response": response, "model": critic.model}
