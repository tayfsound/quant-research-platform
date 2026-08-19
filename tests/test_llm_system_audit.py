"""services/llm_system_audit.py — Faz 271.

Gerçek NVIDIA çağrısı ağ bağımlı olduğu için ask_with_tools mock'lanıyor
(NvidiaDecisionCritic'in kendisi ayrı testlerde doğrulanmış); burada
sadece run_system_audit()'in gerçek DB'ye doğru satırı yazdığı ve
propose_code_change çağrılarını doğru saydığı doğrulanıyor."""
from unittest.mock import AsyncMock, patch

from database.repositories.llm_audit_run_repository import LLMAuditRunRepository
from database.session_factory import SessionFactory
from services.llm_system_audit import run_system_audit


def test_run_system_audit_persists_response_with_no_proposals():
    mock_result = {
        "response": "Son 24 saatte belirgin bir sorun görmedim.",
        "tool_calls": [
            {"tool": "get_recent_performance_summary", "arguments": {"hours": 24}, "result": {"ai_automatic_win_rate": 0.55}},
        ],
    }
    with patch("services.llm_system_audit.NvidiaDecisionCritic.ask_with_tools", new=AsyncMock(return_value=mock_result)):
        result = run_system_audit()

    assert result["response"] == "Son 24 saatte belirgin bir sorun görmedim."
    assert result["tool_call_count"] == 1
    assert result["proposals_created"] == 0

    with SessionFactory.get_session() as session:
        runs = LLMAuditRunRepository(session).get_recent(limit=1)
    assert runs[0]["id"] == result["id"]
    assert runs[0]["proposals_created"] == 0


def test_run_system_audit_counts_real_proposal_creations():
    mock_result = {
        "response": "Bir sorun buldum, öneri oluşturdum.",
        "tool_calls": [
            {"tool": "get_recent_performance_summary", "arguments": {}, "result": {"ai_automatic_win_rate": 0.3}},
            {
                "tool": "propose_code_change",
                "arguments": {"file_path": "x.py", "title": "t", "description": "d", "diff": "-", "rationale": "r"},
                "result": {"proposal_id": "11111111-1111-1111-1111-111111111111", "status": "pending"},
            },
            # Başarısız bir araç çağrısı (hata döndü) — sayılmamalı.
            {"tool": "propose_code_change", "arguments": {}, "result": {"error": "boom"}},
        ],
    }
    with patch("services.llm_system_audit.NvidiaDecisionCritic.ask_with_tools", new=AsyncMock(return_value=mock_result)):
        result = run_system_audit()

    assert result["proposals_created"] == 1
    assert result["tool_call_count"] == 3


def test_run_system_audit_defaults_to_ok_status_when_ask_with_tools_omits_it():
    mock_result = {"response": "Sorun görmedim.", "tool_calls": []}
    with patch("services.llm_system_audit.NvidiaDecisionCritic.ask_with_tools", new=AsyncMock(return_value=mock_result)):
        result = run_system_audit()
    assert result["status"] == "ok"


def test_run_system_audit_persists_a_technical_failure_status_not_as_a_normal_finding():
    """Faz 282 — kritik bulgu: "Araç çağrı döngüsü sınırına ulaşıldı" gibi
    teknik başarısızlıklar önceden normal bir çalıştırma gibi
    kaydediliyordu — status alanı artık bunu gerçek bir bulgudan ayırt
    ediyor."""
    mock_result = {
        "response": "Araç çağrı döngüsü sınırına ulaşıldı, net bir cevap üretemedim.",
        "tool_calls": [],
        "status": "tool_loop_limit",
    }
    with patch("services.llm_system_audit.NvidiaDecisionCritic.ask_with_tools", new=AsyncMock(return_value=mock_result)):
        result = run_system_audit()

    assert result["status"] == "tool_loop_limit"

    with SessionFactory.get_session() as session:
        runs = LLMAuditRunRepository(session).get_recent(limit=1)
    assert runs[0]["status"] == "tool_loop_limit"
