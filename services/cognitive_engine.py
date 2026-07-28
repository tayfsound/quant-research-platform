"""Cognitive Engine — opinions akışı + RecordingStage."""
from contracts.context import CognitiveCycleContext
from contracts.belief import Belief
from contracts.agent import AgentOpinion
from agents.registry import AgentRegistry
from engines.risk_engine import RiskEngine
from services.guardrail_stage import GuardrailStage
from engines.cognitive_pipeline import (
    MemoryStage, KnowledgeStage, CouncilStage, MetaStage,
    DecisionFusionStage, RecordingStage,
)

class CognitiveEngine:
    def __init__(self):
        registry = AgentRegistry.create_default()

        self.guardrail_stage = GuardrailStage(RiskEngine())
        self.memory_stage = MemoryStage()
        self.knowledge_stage = KnowledgeStage()
        self.council_stage = CouncilStage(registry)
        self.meta_stage = MetaStage()
        self.decision_fusion = DecisionFusionStage()
        self.record_stage = RecordingStage()

    def run(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        ctx, should_continue = self.guardrail_stage.evaluate(ctx)
        if not should_continue:
            return self.record_stage.execute(ctx, None, [])

        ctx = self.memory_stage.execute(ctx)
        ctx = self.knowledge_stage.execute(ctx)
        ctx, belief, opinions = self.council_stage.execute(ctx)
        ctx = self.meta_stage.execute(ctx, belief)
        ctx = self.decision_fusion.execute(ctx, belief)
        ctx = self.record_stage.execute(ctx, belief, opinions)
        return ctx
