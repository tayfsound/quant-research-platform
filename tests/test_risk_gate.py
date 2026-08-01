"""RiskGateStage integration tests."""
from unittest.mock import MagicMock
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import RiskGateStage

class FakeLimit:
    value = 0.5

class FakeEval:
    verdict = ""
    reasons = []

def test_rejects_oversized():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 1.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    
    ctx = stage.execute(ctx)
    
    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "POST_FUSION_SIZE_EXCEEDED" for r in ctx.risk.evaluation.reasons)

def test_approves_valid():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 0.3
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    
    ctx = stage.execute(ctx)
    
    assert ctx.risk.evaluation.verdict == "approved"
    assert ctx.decision.final_size == 0.3
