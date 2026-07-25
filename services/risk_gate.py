"""Risk Gate — ActionType günceller."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType, DecisionReason

class RiskGate:
    def __init__(self, max_position_size: float = 1.0, max_drawdown: float = 0.15):
        self.max_position_size = max_position_size
        self.max_drawdown = max_drawdown

    def evaluate(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        reasons = []

        if ctx.decision.action == ActionType.WAIT:
            ctx.risk.evaluation.verdict = "approved"
            return ctx

        if ctx.decision.final_size > self.max_position_size:
            reasons.append(f"Size {ctx.decision.final_size} exceeds max {self.max_position_size}")

        if ctx.risk.current_drawdown >= self.max_drawdown:
            reasons.append(f"Drawdown {ctx.risk.current_drawdown:.1%} exceeds limit")

        if reasons:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.reason = DecisionReason.HIGH_RISK
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
        else:
            ctx.risk.evaluation.verdict = "approved"

        return ctx
