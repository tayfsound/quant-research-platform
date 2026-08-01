"""Replay Engine integration testleri."""
import pytest
from unittest.mock import MagicMock
from services.replay_engine import ReplayEngine


def test_replay_engine_lists_sessions():
    """ReplayEngine mevcut session'lari listelemeli."""
    mock_decision_repo = MagicMock()
    mock_decision_repo.list_recent.return_value = [
        {"symbol": "BTCUSDT", "direction": "LONG"},
        {"symbol": "ETHUSDT", "direction": "SHORT"},
    ]
    engine = ReplayEngine(decision_repo=mock_decision_repo)
    sessions = engine.list_available_sessions()
    assert isinstance(sessions, list)
    assert len(sessions) == 2
    assert sessions[0]["symbol"] == "BTCUSDT"


def test_replay_engine_requires_repositories():
    """Repo olmadan replay hata donmeli."""
    engine = ReplayEngine()
    result = engine.run_replay("test_session")
    assert "error" in result
    assert result["error"] == "repositories_not_configured"


def test_replay_engine_runs_with_mock_data():
    """Mock belief+decision ile replay calismali."""
    mock_belief_repo = MagicMock()
    mock_belief_repo.get_latest.return_value = [
        {"id": "b1", "symbol": "BTCUSDT", "direction": "LONG", "strength": 0.8}
    ]
    mock_decision_repo = MagicMock()
    mock_decision_repo.get_by_symbol.return_value = [
        {"id": "d1", "symbol": "BTCUSDT", "direction": "LONG"}
    ]

    engine = ReplayEngine(
        belief_repo=mock_belief_repo,
        decision_repo=mock_decision_repo,
    )

    # CognitiveEngine'i mock'la — property yerine _engine attribute'unu set et
    mock_eng = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.decision.proposed_direction = "LONG"
    mock_eng.run.return_value = mock_ctx
    engine._engine = mock_eng

    result = engine.run_replay("session_BTCUSDT", symbol="BTCUSDT")
    assert result["belief_count"] == 1
    assert result["decision_count"] == 1
    assert result["session_id"] == "session_BTCUSDT"
    assert "match_rate" in result


def test_replay_integrity_check():
    """Replay oncesi veri butunlugu kontrol edilmeli."""
    mock_belief_repo = MagicMock()
    mock_belief_repo.get_latest.return_value = [{"id": "b1"}]
    mock_decision_repo = MagicMock()
    mock_decision_repo.list_recent.return_value = [{"id": "d1"}]

    engine = ReplayEngine(
        belief_repo=mock_belief_repo,
        decision_repo=mock_decision_repo,
    )
    integrity = engine.validate_replay_integrity("session_1")
    assert integrity["valid"] is True
    assert integrity["belief_count"] == 1
    assert integrity["decision_count"] == 1


def test_replay_integrity_fails_without_data():
    """Veri yoksa replay gecersiz olmali."""
    mock_belief_repo = MagicMock()
    mock_belief_repo.get_latest.return_value = []
    mock_decision_repo = MagicMock()
    mock_decision_repo.list_recent.return_value = []

    engine = ReplayEngine(
        belief_repo=mock_belief_repo,
        decision_repo=mock_decision_repo,
    )
    integrity = engine.validate_replay_integrity("session_1")
    assert integrity["valid"] is False
