"""Cognitive Engine — opinions akışı + RecordingStage."""
from contracts.context import CognitiveCycleContext
from agents.registry import AgentRegistry
from engines.cognitive_pipeline import MemoryStage, CouncilStage, MetaStage, RiskStage, RecordingStage

class CognitiveEngine:
    def __init__(self):
        registry = AgentRegistry.create_default()

        self.memory_stage = MemoryStage()
        self.council_stage = CouncilStage(registry)
        self.meta_stage = MetaStage()
        self.risk_stage = RiskStage()
        self.record_stage = RecordingStage()

    def run(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        ctx = self.memory_stage.execute(ctx)
        ctx, belief, opinions = self.council_stage.execute(ctx)
        ctx = self.meta_stage.execute(ctx, belief)
        ctx = self.risk_stage.execute(ctx)
        ctx = self.record_stage.execute(ctx, belief, opinions)
        return ctx
