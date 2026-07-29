"""Cognitive Engine — opinions akışı + RecordingStage + feedback loop."""
from contracts.context import CognitiveCycleContext
from contracts.belief import Belief
from contracts.agent import AgentOpinion
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from agents.registry import AgentRegistry
from database.connection import get_session
from engines.risk_engine import RiskEngine
from engines.cognitive_pipeline import (
    MemoryStage, KnowledgeStage, CouncilStage, MetaStage,
    DecisionFusionStage, RecordingStage,
)
from database.repositories.decision_persistor import DecisionPersistor
from services.guardrail_stage import GuardrailStage
from services.learning_loop import LearningLoop
from services.outcome_evaluator import OutcomeEvaluator
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


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

        self.outcome_evaluator = OutcomeEvaluator()
        self.learning_loop = LearningLoop()
        self.weight_repository = WeightRepository()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.learning_loop.agent_memory,
            weight_repository=self.weight_repository,
        )

    def run(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        ctx, should_continue = self.guardrail_stage.evaluate(ctx)
        if not should_continue:
            event = self.record_stage.execute(ctx, None, [])
            self._persist_and_learn(event, ctx)
            return ctx

        ctx = self.memory_stage.execute(ctx)
        ctx = self.knowledge_stage.execute(ctx)
        ctx, belief, opinions = self.council_stage.execute(ctx)
        ctx = self.meta_stage.execute(ctx, belief)
        ctx = self.decision_fusion.execute(ctx, belief)
        event = self.record_stage.execute(ctx, belief, opinions)
        self._persist_and_learn(event, ctx)
        return ctx

    def _persist_and_learn(
        self,
        event,
        ctx: CognitiveCycleContext,
    ) -> None:
        """Persist decision to DB and run post-execution feedback loop."""
        session = get_session()
        try:
            DecisionPersistor(session).persist(event)
        finally:
            session.close()

        if ctx.outcome is None:
            return

        evaluation = self.outcome_evaluator.evaluate(event, ctx.outcome)
        self.learning_loop.record(event, evaluation)

        new_weights = self.weight_optimizer.optimize(
            agents=event.agent_opinions,
            outcome=evaluation,
        )

        previous = self.weight_repository.get_latest()
        snapshot = AgentWeightSnapshot(
            weights=new_weights,
            previous_snapshot_id=previous.id if previous else None,
            reason="feedback_loop_update",
        ).finalize()

        self.weight_repository.save(snapshot)
