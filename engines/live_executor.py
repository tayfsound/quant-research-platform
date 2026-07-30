"""Live Executor — Risk Engine zorunlu, sınırlı yetki."""
from contracts.context import CognitiveCycleContext
from engines.risk_engine import RiskEngine


class LiveExecutor:
    def __init__(self, risk_engine: RiskEngine):
        self.risk_engine = risk_engine

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        ctx = self.risk_engine.execute(ctx)
        if ctx.risk.evaluation.verdict != "approved":
            ctx.outcome = {"executed": False, "reason": "risk_rejected"}
            return ctx
        # Gerçek emir (stub)
        ctx.outcome = {"executed": True, "mode": "live", "size": ctx.decision.risk_adjusted_size}
        return ctx
