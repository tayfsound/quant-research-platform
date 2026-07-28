"""Guardrail Stage — Risk engine runs FIRST and can halt the pipeline."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType


class GuardrailStage:
    """Hash-validated risk gate that runs before any agent computation."""

    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def evaluate(self, ctx: CognitiveCycleContext) -> tuple[CognitiveCycleContext, bool]:
        result = self.risk_engine.execute(ctx)

        if result.risk.evaluation.verdict == "rejected":
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = result.risk.evaluation.reasons
            return ctx, False

        return ctx, True
