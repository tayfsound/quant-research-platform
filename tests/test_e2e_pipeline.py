"""E2E: RiskGateStage wired in engine chain."""
from unittest.mock import patch


def test_risk_gate_in_engine_chain():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from services.cognitive_engine import CognitiveEngine
        engine = CognitiveEngine()
        assert hasattr(engine, "risk_gate_stage")
        ctx = CognitiveCycleContext()
        ctx.market.symbol = "BTCUSDT"
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.confidence = 0.8
        ctx.risk.limits = {}
        ctx.risk.current_drawdown = 0.0
        ctx = engine.run(ctx, persist=False)
        assert ctx.risk.evaluation.verdict in ("approved", "rejected")
