"""POST /api/v1/llm-critic/ask + öneri kuyruğu endpoint'leri.

Faz 270 — kullanıcı isteği: LLM artık gerçek kod/DB araçlarına sahip
(ask_with_tools(), bkz. llm_reasoner.py + llm_tools.py) ve kod
değişikliği önerebiliyor (propose_code_change) — ama bunlar HİÇBİR ZAMAN
otomatik uygulanmıyor, sadece code_change_proposals kuyruğuna ekleniyor.
Gerçek NVIDIA çağrısı ağ bağımlı (~90s) olduğu için burada mock'lanıyor
— NvidiaDecisionCritic'in kendisi ayrı, izole testlerde zaten
doğrulanmış (tests/contract/test_llm_explainer.py, tests/test_llm_tools.py)."""
from unittest.mock import AsyncMock, patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_ask_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.post("/api/v1/llm-critic/ask", json={"message": "test"})
        assert response.status_code in (401, 403)


def test_ask_uses_tool_calling_and_returns_tool_call_trace():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        mock_result = {
            "response": "Gerçek AI-otomatik kazanma oranı %19.",
            "tool_calls": [{"tool": "get_recent_performance_summary", "arguments": {}, "result": {"ai_automatic_win_rate": 0.19}}],
        }
        with patch("llm_reasoner.NvidiaDecisionCritic.ask_with_tools", new=AsyncMock(return_value=mock_result)):
            response = client.post(
                "/api/v1/llm-critic/ask",
                json={"message": "Bugünkü kazanma oranı nedir?"},
                headers=make_authed_headers(Role.VIEWER),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Gerçek AI-otomatik kazanma oranı %19."
        assert body["tool_calls"][0]["tool"] == "get_recent_performance_summary"


def test_list_audit_runs_requires_auth():
    client = _client()
    response = client.get("/api/v1/llm-critic/audit-runs")
    assert response.status_code in (401, 403)


def test_list_audit_runs_returns_real_saved_row():
    """Faz 271 — kullanıcı isteği: LLM'in periyodik denetiminin (services/
    llm_system_audit.py) geçmişi panelde görünmeli, "hiçbir şey bulamadım"
    dahil."""
    from contracts.llm_audit_run import LLMAuditRun
    from database.repositories.llm_audit_run_repository import LLMAuditRunRepository
    from database.session_factory import SessionFactory

    run = LLMAuditRun(
        response="Test denetim yanıtı.",
        tool_calls=[{"tool": "get_recent_performance_summary", "arguments": {}, "result": {}}],
        proposals_created=0,
    )
    with SessionFactory.get_session() as session:
        LLMAuditRunRepository(session).save(run)

    client = _client()
    response = client.get("/api/v1/llm-critic/audit-runs", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["runs"]]
    assert str(run.id) in ids


def test_list_proposals_requires_auth():
    client = _client()
    response = client.get("/api/v1/llm-critic/proposals")
    assert response.status_code in (401, 403)


def test_list_pending_proposals_returns_real_saved_row():
    from contracts.code_change_proposal import CodeChangeProposal
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    proposal = CodeChangeProposal(
        title="Test öneri", file_path="services/example.py",
        description="test açıklama", diff="--- a\n+++ b\n", rationale="test gerekçe",
    )
    with SessionFactory.get_session() as session:
        CodeChangeProposalRepository(session).save(proposal)

    client = _client()
    response = client.get(
        "/api/v1/llm-critic/proposals?status=pending",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()["proposals"]]
    assert str(proposal.id) in ids


def test_approve_proposal_requires_operator_role():
    from contracts.code_change_proposal import CodeChangeProposal
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    proposal = CodeChangeProposal(
        title="Test öneri 2", file_path="services/example.py",
        description="test", diff="diff", rationale="test",
    )
    with SessionFactory.get_session() as session:
        CodeChangeProposalRepository(session).save(proposal)

    client = _client()
    response = client.post(
        f"/api/v1/llm-critic/proposals/{proposal.id}/approve",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert response.status_code == 403


def test_approve_proposal_changes_status_and_never_touches_disk():
    from contracts.code_change_proposal import CodeChangeProposal
    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    proposal = CodeChangeProposal(
        title="Test öneri 3", file_path="services/example.py",
        description="test", diff="diff", rationale="test",
    )
    with SessionFactory.get_session() as session:
        CodeChangeProposalRepository(session).save(proposal)

    client = _client()
    response = client.post(
        f"/api/v1/llm-critic/proposals/{proposal.id}/approve",
        headers=make_authed_headers(Role.OPERATOR),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    with SessionFactory.get_session() as session:
        row = CodeChangeProposalRepository(session).get_by_id(str(proposal.id))
    assert row["status"] == "approved"
    assert row["reviewed_by"] is not None


def test_reject_unknown_proposal_returns_404():
    import uuid

    client = _client()
    response = client.post(
        f"/api/v1/llm-critic/proposals/{uuid.uuid4()}/reject",
        headers=make_authed_headers(Role.OPERATOR),
    )
    assert response.status_code == 404
