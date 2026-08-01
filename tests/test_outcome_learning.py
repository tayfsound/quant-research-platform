"""Outcome → learning trigger integration."""
from unittest.mock import patch

class FakeLimit:
    value = 10.0
    def verify(self, secret):
        return True

def test_outcome_none_no_learning():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.cognitive_engine import CognitiveEngine
            from contracts.context import CognitiveCycleContext
            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            ctx.risk.limits = {"max_position_size": FakeLimit()}
            ctx.risk.current_drawdown = 0.0
            
            with patch.object(engine.learning_loop, "record") as mock_record:
                engine.run(ctx, persist=True)
                mock_record.assert_not_called()

def test_outcome_triggers_learning():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.cognitive_engine import CognitiveEngine
            from contracts.context import CognitiveCycleContext
            from contracts.outcome import TradeOutcome
            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            ctx.risk.limits = {"max_position_size": FakeLimit()}
            ctx.risk.current_drawdown = 0.0
            
            ctx = engine.run(ctx, persist=False)
            ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)
            
            with patch.object(engine.learning_loop, "record") as mock_record:
                with patch.object(engine.weight_optimizer, "optimize") as mock_opt:
                    mock_opt.return_value = {"technical": 1.2}
                    engine.finalize(ctx)
                    mock_record.assert_called_once()
