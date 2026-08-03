"""ReplayEngine E2E — decision replay from DB + snapshot restore."""
from unittest.mock import patch, MagicMock

def test_replay_decision_from_db():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.replay_engine import ReplayEngine
            from contracts.context import CognitiveCycleContext
            
            engine = ReplayEngine()
            
            # Mock decision repo with snapshot
            mock_decision_repo = MagicMock()
            mock_decision_repo.get_by_id.return_value = {
                "symbol": "BTCUSDT",
                "proposed_direction": "LONG",
                "confidence": 0.8,
                "market_snapshot": {
                    "raw_snapshot": {"rsi": 30, "ema": 100, "macd": 0.5}
                }
            }
            engine.decision_repo = mock_decision_repo
            
            result = engine.replay_decision("test-id")
            
            assert result["decision_id"] == "test-id"
            assert result["symbol"] == "BTCUSDT"
            assert result["snapshot_restored"] is True
            mock_decision_repo.get_by_id.assert_called_once_with("test-id")
