"""Execution Router — mode'a göre boundary seçer."""
from config import get_settings
from contracts.context import CognitiveCycleContext
from contracts.execution_mode import ExecutionMode
from engines.live_executor import LiveExecutor
from engines.risk_engine import RiskEngine
from engines.sandbox_executor import SandboxExecutor


class ExecutionRouter:
    def __init__(self):
        self.sandbox = SandboxExecutor()
        # Gerçek bulgu (kod incelemesi, 2026-08-05): hardcoded "production-secret"
        # string literal kullanılıyordu — CognitiveEngine'in gerçek RiskEngine'i
        # zaten settings.SECRET_KEY kullanıyor (gap #15); bu ayrı, tamamen farklı
        # bir sabit secret'la imza doğrulaması hiçbir zaman gerçek anlamda
        # çalışmazdı (aynı yerde imzalanmış bir limit burada asla doğrulanmaz).
        self.risk_engine = RiskEngine(secret=get_settings().SECRET_KEY)
        self.live = LiveExecutor(self.risk_engine)

    def route(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if ctx.mode == ExecutionMode.EXPERIMENT or ctx.mode == ExecutionMode.PAPER:
            return self.sandbox.execute(ctx)
        elif ctx.mode == ExecutionMode.LIVE:
            ctx = self.risk_engine.execute(ctx)
            if ctx.risk.evaluation.verdict == "approved":
                ctx = self.live.execute(ctx)
            else:
                ctx.outcome = {"executed": False, "reason": "risk_rejected"}
        return ctx
