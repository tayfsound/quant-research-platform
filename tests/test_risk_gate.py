"""Risk Gate testleri — düzeltilmiş."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType, Decision
from services.risk_gate import RiskGate

def test_risk_gate_approves_small_position():
    gate = RiskGate(max_position_size=1.0)
    ctx = CognitiveCycleContext(
        decision=Decision(final_size=0.5, action=ActionType.ENTER_LONG),
    )
    result = gate.evaluate(ctx)
    assert result.risk.evaluation.verdict == "approved"

def test_risk_gate_rejects_large_position():
    gate = RiskGate(max_position_size=0.3)
    ctx = CognitiveCycleContext(
        decision=Decision(final_size=10.0, action=ActionType.ENTER_LONG),
    )
    result = gate.evaluate(ctx)
    assert result.risk.evaluation.verdict == "rejected"
    assert result.decision.action == ActionType.WAIT

def test_risk_gate_rejects_on_drawdown():
    gate = RiskGate(max_drawdown=0.1)
    ctx = CognitiveCycleContext(
        risk={"current_drawdown": 0.15},
        decision=Decision(final_size=0.5, action=ActionType.ENTER_LONG),
    )
    result = gate.evaluate(ctx)
    assert result.risk.evaluation.verdict == "rejected"
    assert result.decision.action == ActionType.WAIT
