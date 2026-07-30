"""Orchestrator dict kararlari <-> CognitiveCycleContext koprusu."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType, Decision, DecisionReason
from contracts.contexts.risk import RiskContext, RiskLimitEntry, RiskEvaluation, RiskReason

def direction_to_action(direction: str) -> ActionType:
    d = (direction or "").upper()
    if d == "LONG":
        return ActionType.ENTER_LONG
    if d == "SHORT":
        return ActionType.ENTER_SHORT
    return ActionType.WAIT

def build_cycle_context(
    *,
    direction: str,
    size: float,
    current_drawdown: float = 0.0,
    max_position_size: float = 1.0,
    max_drawdown: float = 0.15,
) -> CognitiveCycleContext:
    action = direction_to_action(direction)
    decision = Decision(
        proposed_direction=direction,
        proposed_size=size,
        final_direction=direction,
        final_size=size if action != ActionType.WAIT else 0.0,
        action=action,
        reason=DecisionReason.STRONG_SIGNAL if action != ActionType.WAIT else DecisionReason.NO_SIGNAL,
        confidence=0.6,
        uncertainty=0.4,
    )
    risk = RiskContext(
        limits={
            "max_position_size": RiskLimitEntry(value=max_position_size, hash=""),
            "max_drawdown": RiskLimitEntry(value=max_drawdown, hash=""),
        },
        current_drawdown=current_drawdown,
        evaluation=RiskEvaluation(),
    )
    return CognitiveCycleContext(decision=decision, risk=risk)

def apply_gate_result(ctx: CognitiveCycleContext) -> dict:
    verdict = ctx.risk.evaluation.verdict or "rejected"
    reasons_raw = ctx.risk.evaluation.reasons
    reason_msgs = []
    for r in reasons_raw:
        if isinstance(r, str):
            reason_msgs.append(r)
        else:
            reason_msgs.append(getattr(r, "message", str(r)))
    
    approved = verdict == "approved" and ctx.decision.action != ActionType.WAIT
    direction = "NEUTRAL"
    if ctx.decision.action == ActionType.ENTER_LONG:
        direction = "LONG"
    elif ctx.decision.action == ActionType.ENTER_SHORT:
        direction = "SHORT"
    
    return {
        "approved": approved,
        "direction": direction,
        "size": ctx.decision.final_size,
        "risk_verdict": verdict,
        "risk_reasons": reason_msgs,
        "action": ctx.decision.action.value,
    }
