"""RiskGate reject → recording triggers, size=0, action=WAIT."""
from unittest.mock import patch

class FakeLimit:
    value = 0.5
    def verify(self, secret):
        return True

def test_risk_gate_reject_records_event():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.cognitive_engine import CognitiveEngine
            from contracts.context import CognitiveCycleContext
            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            ctx.decision.final_size = 1.0
            ctx.risk.limits = {"max_position_size": FakeLimit()}
            ctx.risk.current_drawdown = 0.0
            
            with patch.object(engine.record_stage, "execute") as mock_record:
                engine.run(ctx, persist=True)
                mock_record.assert_called_once()
                recorded_ctx = mock_record.call_args[0][0]
                assert recorded_ctx.decision.action.value == "WAIT"
                assert recorded_ctx.decision.final_size == 0.0
