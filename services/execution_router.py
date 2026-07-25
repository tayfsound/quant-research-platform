"""Execution Router — mode'a göre boundary seçer."""
from contracts.context import CognitiveCycleContext
from contracts.execution_mode import ExecutionMode
from engines.risk_engine import RiskEngine
from engines.sandbox_executor import SandboxExecutor
from engines.live_executor import LiveExecutor

class ExecutionRouter:
    def __init__(self):
        self.sandbox = SandboxExecutor()
        self.risk_engine = RiskEngine(secret="production-secret")
        self.live = LiveExecutor(self.risk_engine)

    def route(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if ctx.mode == ExecutionMode.EXPERIMENT:
            return self.sandbox.execute(ctx)
        elif ctx.mode == ExecutionMode.PAPER:
            return self.sandbox.execute(ctx)
        elif ctx.mode == ExecutionMode.LIVE:
            ctx = self.risk_engine.execute(ctx)
            if ctx.risk.evaluation.verdict == "approved":
                ctx = self.live.execute(ctx)
            else:
                ctx.outcome = {"executed": False, "reason": "risk_rejected"}
        return ctx
