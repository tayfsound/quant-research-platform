"""Research Engine — mode'a göre executor seçer."""
from contracts.context import CognitiveCycleContext
from contracts.execution_mode import ExecutionMode
from engines.observation_pipeline import ObservationPipeline
from engines.knowledge_builder import KnowledgeBuilder
from engines.belief_engine import BeliefEngine
from engines.hypothesis_engine import HypothesisEngine
from engines.risk_engine import RiskEngine
from engines.decision_engine import DecisionEngine
from engines.sandbox_executor import SandboxExecutor
from engines.live_executor import LiveExecutor

class ResearchEngine:
    def __init__(self):
        self.stages = [
            ObservationPipeline(),
            KnowledgeBuilder(),
            BeliefEngine(),
            HypothesisEngine(),
            RiskEngine(),
            DecisionEngine(),
        ]
        self.sandbox = SandboxExecutor()
        self.live = LiveExecutor(RiskEngine(secret="production-secret"))

    def run_cycle(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        for stage in self.stages:
            ctx = stage.execute(ctx)

        if ctx.mode == ExecutionMode.EXPERIMENT:
            ctx = self.sandbox.execute(ctx)
        elif ctx.mode == ExecutionMode.PAPER:
            ctx = self.sandbox.execute(ctx)  # PAPER = simüle
        elif ctx.mode == ExecutionMode.LIVE:
            ctx = self.live.execute(ctx)

        return ctx
