"""ReplayEngine run_replay with mocked repos."""
from unittest.mock import patch, MagicMock

def test_run_replay_with_beliefs_and_decisions():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.replay_engine import ReplayEngine

            mock_belief_repo = MagicMock()
            mock_belief_repo.get_latest.return_value = [
                {"direction": "LONG", "strength": 0.8, "symbol": "BTCUSDT"},
            ]

            mock_decision_repo = MagicMock()
            mock_decision_repo.get_by_symbol.return_value = [
                {"symbol": "BTCUSDT", "proposed_direction": "LONG", "confidence": 0.8},
            ]

            engine = ReplayEngine(belief_repo=mock_belief_repo, decision_repo=mock_decision_repo)
            result = engine.run_replay("session_BTCUSDT", symbol="BTCUSDT")

            assert "error" not in result or result.get("error") is None
            assert result["session_id"] == "session_BTCUSDT"
            assert result["symbol"] == "BTCUSDT"
            mock_belief_repo.get_latest.assert_called_once()
            mock_decision_repo.get_by_symbol.assert_called_once_with("BTCUSDT", limit=100)

def test_run_replay_no_beliefs():
    from services.replay_engine import ReplayEngine
    mock_belief_repo = MagicMock()
    mock_belief_repo.get_latest.return_value = []
    mock_decision_repo = MagicMock()

    engine = ReplayEngine(belief_repo=mock_belief_repo, decision_repo=mock_decision_repo)
    result = engine.run_replay("session_BTCUSDT")

    assert result["error"] == "no_beliefs_found"
