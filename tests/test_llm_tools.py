"""Faz 270 — llm_tools.py: Respond sekmesindeki LLM'e gerçek kod/DB
erişimi veren araçlar. Bunlar OLMADAN LLM'in "kodu taradım" deyip
tamamen uydurma sayılar ürettiği (stop/TP mesafeleri, gerçekte olmayan
bir R/R oranı) bu oturumda gerçekten yakalandı — bu testler her aracın
GERÇEK veri döndürdüğünü, hiçbir zaman uydurmadığını doğruluyor."""
from pathlib import Path

import llm_tools


def test_get_recent_performance_summary_returns_real_shape():
    result = llm_tools.get_recent_performance_summary(hours=24)
    assert "ai_automatic_closed_trades" in result
    assert "manually_closed_trades" in result
    assert "current_stop_atr_mult" in result
    assert result["window_hours"] == 24


def test_classify_recent_stop_loss_failures_returns_real_shape():
    result = llm_tools.classify_recent_stop_loss_failures(hours=90)
    assert "total_stop_loss_trades" in result
    assert "direction_error_count" in result
    assert "barrier_error_count" in result


def test_train_and_evaluate_meta_label_model_returns_real_shape():
    result = llm_tools.train_and_evaluate_meta_label_model(window=50, min_samples=10_000_000)
    assert result == {"trained": False, "reason": "insufficient_samples_or_single_class"}


def test_read_source_file_returns_real_content():
    result = llm_tools.read_source_file("llm_tools.py", start_line=1, end_line=5)
    assert "error" not in result
    assert "1:" in result["content"]
    assert result["total_lines"] > 5


def test_read_source_file_rejects_path_traversal():
    result = llm_tools.read_source_file("../../../etc/passwd")
    assert result == {"error": "path_not_allowed"}


def test_read_source_file_blocks_env_and_secret_files():
    for blocked in (".env", "some_secret.py", "credential_store.py"):
        result = llm_tools.read_source_file(blocked)
        assert result.get("error") == "path_not_allowed"


def test_read_source_file_returns_not_found_for_missing_file():
    result = llm_tools.read_source_file("this_file_definitely_does_not_exist.py")
    assert result == {"error": "file_not_found"}


def test_read_source_file_caps_returned_lines():
    result = llm_tools.read_source_file("llm_tools.py", start_line=1, end_line=100000)
    returned = result["returned_lines"]
    start, end = (int(x) for x in returned.split("-"))
    assert end - start + 1 <= llm_tools._MAX_FILE_READ_LINES


def test_search_code_finds_a_real_known_symbol():
    result = llm_tools.search_code("class NvidiaDecisionCritic")
    assert any(m["path"] == "llm_reasoner.py" for m in result["matches"])


def test_search_code_returns_empty_for_nonsense_query():
    # Sorgu bilerek parçalar halinde birleştiriliyor — tek parça halinde
    # yazılsaydı bu test dosyasının KENDİSİ bir "eşleşme" olurdu.
    nonsense_query = "xyzzy" + "_no_such_symbol_" + "qqq123"
    result = llm_tools.search_code(nonsense_query)
    assert result["matches"] == []
    assert result["truncated"] is False


def test_propose_code_change_never_writes_to_disk_only_queues(tmp_path):
    target = Path("services/decision_fusion.py")
    original_content = target.read_text()

    result = llm_tools.propose_code_change(
        file_path=str(target),
        title="Test öneri — asla uygulanmamalı",
        description="test",
        diff="--- a/services/decision_fusion.py\n+++ b/services/decision_fusion.py\n",
        rationale="test",
    )
    assert result["status"] == "pending"
    assert "proposal_id" in result
    # Gerçek dosya HİÇ değişmemiş olmalı.
    assert target.read_text() == original_content

    from database.repositories.code_change_proposal_repository import CodeChangeProposalRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        row = CodeChangeProposalRepository(session).get_by_id(result["proposal_id"])
    assert row is not None
    assert row["status"] == "pending"
    assert row["title"] == "Test öneri — asla uygulanmamalı"
