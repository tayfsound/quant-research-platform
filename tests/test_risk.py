"""Risk testleri — contract-first yaklaşım."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import Decision, ActionType
from contracts.contexts.risk import RiskContext
from services.risk_gate import RiskGate

def test_risk_gate_approves_small_trade():
    gate = RiskGate(max_position_size=1.0)
    ctx = CognitiveCycleContext(
        risk=RiskContext(),
        decision=Decision(final_size=0.5, action=ActionType.ENTER_LONG),
    )
    result = gate.evaluate(ctx)
    assert result.risk.evaluation.verdict == "approved"

def test_risk_gate_rejects_large_trade():
    gate = RiskGate(max_position_size=0.3)
    ctx = CognitiveCycleContext(
        risk=RiskContext(),
        decision=Decision(final_size=10.0, action=ActionType.ENTER_LONG),
    )
    result = gate.evaluate(ctx)
    assert result.risk.evaluation.verdict == "rejected"

def test_risk_gate_waits_on_drawdown():
    gate = RiskGate(max_drawdown=0.1)
    ctx = CognitiveCycleContext(
        risk=RiskContext(current_drawdown=0.15),
        decision=Decision(final_size=0.5, action=ActionType.ENTER_LONG),
    )
    result = gate.evaluate(ctx)
    assert result.risk.evaluation.verdict == "rejected"
