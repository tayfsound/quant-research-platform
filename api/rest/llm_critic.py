"""LLM Decision Critic API — Faz 268-sonrası (kullanıcı isteği).

Dashboard'da serbest metin soru/cevap sekmesi için — llm_reasoner.py::
NvidiaDecisionCritic.ask_with_tools() gerçek NVIDIA NIM API'sini
(deepseek-v4-flash) ve gerçek kod/DB araçlarını (llm_tools.py) kullanır.

Faz 270: LLM artık kod değişikliği ÖNERebiliyor (propose_code_change
aracı) — ama bunlar HİÇBİR ZAMAN otomatik uygulanmıyor, sadece
code_change_proposals kuyruğuna ekleniyor. Buradaki approve/reject
endpoint'leri SADECE durumu değiştirir, hiçbir dosyayı diske yazmaz —
gerçek uygulama daima ayrı, insan tarafından yürütülen bir adımdır
("teşhis + öneri kuyruğu evet, otomatik self-deploy hayır")."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from contracts.auth import Role
from services.auth_service import AuthContext, get_current_user, require_role

router = APIRouter(prefix="/llm-critic", tags=["llm-critic"])


class AskRequest(BaseModel):
    message: str


@router.post("/ask")
async def ask(body: AskRequest, user: AuthContext = Depends(get_current_user)):
    from llm_reasoner import NvidiaDecisionCritic

    critic = NvidiaDecisionCritic()
    result = await critic.ask_with_tools(body.message)
    return {"response": result["response"], "tool_calls": result["tool_calls"], "model": critic.model}


@router.get("/audit-runs")
def list_audit_runs(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    """Faz 271 — kullanıcı isteği: LLM'in periyodik sistem denetiminin
    (services/llm_system_audit.py, her 6 saatte bir) GEÇMİŞİNİ göster —
    "hiçbir şey bulamadım" dahil, çünkü aksi halde denetimin gerçekten
    çalıştığına dair hiçbir iz kullanıcıya görünmezdi."""
    from database.repositories.llm_audit_run_repository import LLMAuditRunRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        runs = LLMAuditRunRepository(session).get_recent(limit=limit)
    return {"runs": runs}


@router.get("/proposals")
def list_proposals(status: str | None = None, limit: int = 50, user: AuthContext = Depends(get_current_user)):
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = CodeChangeProposalRepository(session)
        proposals = repo.get_pending(limit=limit) if status == "pending" else repo.get_all(limit=limit)
    return {"proposals": proposals}


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = CodeChangeProposalRepository(session)
        ok = repo.decide(proposal_id, "approved", reviewed_by=user.username)
        if not ok:
            raise HTTPException(status_code=404, detail="proposal_not_found_or_not_pending")
        return repo.get_by_id(proposal_id)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, user: AuthContext = Depends(require_role(Role.OPERATOR))):
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = CodeChangeProposalRepository(session)
        ok = repo.decide(proposal_id, "rejected", reviewed_by=user.username)
        if not ok:
            raise HTTPException(status_code=404, detail="proposal_not_found_or_not_pending")
        return repo.get_by_id(proposal_id)
