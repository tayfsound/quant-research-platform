"""ReplayEngine API — list sessions + run replay."""
from unittest.mock import patch, MagicMock

def test_list_sessions_returns_decisions():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.replay_engine import ReplayEngine
            
            mock_decision_repo = MagicMock()
            mock_decision_repo.list_recent.return_value = [
                {"symbol": "BTCUSDT", "id": "d1"},
                {"symbol": "BTCUSDT", "id": "d2"},
                {"symbol": "ETHUSDT", "id": "d3"},
            ]
            
            engine = ReplayEngine(decision_repo=mock_decision_repo)
            sessions = engine.list_available_sessions()
            
            assert len(sessions) == 2
            symbols = {s["symbol"] for s in sessions}
            assert symbols == {"BTCUSDT", "ETHUSDT"}

def test_run_replay_needs_repos():
    from services.replay_engine import ReplayEngine
    engine = ReplayEngine()
    result = engine.run_replay("session_BTCUSDT")
    assert result["error"] == "repositories_not_configured"

def test_engine_lazy_init():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.replay_engine import ReplayEngine
            engine = ReplayEngine()
            assert engine._engine is None
            _ = engine.engine
            assert engine._engine is not None
