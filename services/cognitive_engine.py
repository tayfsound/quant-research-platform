"""Cognitive Engine — opinions akışı + RecordingStage + feedback loop."""
from agents.registry import AgentRegistry
from config import get_settings
from contracts.context import CognitiveCycleContext
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor
from engines.cognitive_pipeline import (
    BinderStage,
    CouncilStage,
    DecisionFusionStage,
    KnowledgeStage,
    MemoryStage,
    MetaStage,
    RecordingStage,
    RiskGateStage,
    RiskTargetStage,
)
from engines.memory_engine import MemoryEngine
from engines.risk_engine import RiskEngine
from services.guardrail_stage import GuardrailStage
from services.learning_loop import LearningLoop
from services.outcome_evaluator import OutcomeEvaluator
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


class CognitiveEngine:
    def __init__(self, pinned_weight_snapshot_id=None):
        """pinned_weight_snapshot_id: if set, every decision uses this exact
        weight snapshot instead of WeightRepository.get_latest() — required
        for backtest determinism (see backtest/cognitive_backtest_runner.py)
        so a simulated historical decision can't use weights learned from
        data past that point in time."""
        registry = AgentRegistry.create_default()

        # Gap #15: RiskLimitEntry.verify(secret) needs a real secret to mean
        # anything — an empty secret (the old default) makes hash-signed
        # limits unverifiable in any meaningful sense. SECRET_KEY empty in
        # dev is fine: RiskLimitEntry.verify() already treats hash="" as
        # "development mode, always pass".
        self.guardrail_stage = GuardrailStage(RiskEngine(secret=get_settings().SECRET_KEY))
        self.memory_stage = MemoryStage()
        self.knowledge_stage = KnowledgeStage()
        self.binder_stage = BinderStage()
        self.council_stage = CouncilStage(registry, pinned_weight_snapshot_id=pinned_weight_snapshot_id)
        self.meta_stage = MetaStage()
        self.risk_target_stage = RiskTargetStage()
        self.decision_fusion = DecisionFusionStage()
        self.record_stage = RecordingStage()
        self.risk_gate_stage = RiskGateStage(self.guardrail_stage.risk_engine)
        # Gap #8: MemoryEngine existed, worked (once its own two bugs were
        # fixed — see services/memory_consolidator.py), and was never called
        # from anywhere. Only wired into finalize(), not run(): backtests
        # call run(persist=False) and never finalize(), so replaying
        # thousands of historical bars doesn't spam real embedding
        # computation + episodic DB writes for synthetic data.
        self.memory_engine = MemoryEngine()

        self.outcome_evaluator = OutcomeEvaluator()
        self.learning_loop = LearningLoop()
        self.weight_repository = WeightRepository()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.learning_loop.agent_memory,
            weight_repository=self.weight_repository,
        )

    def run(self, ctx: CognitiveCycleContext, *, persist: bool = True) -> CognitiveCycleContext:
        ctx, should_continue = self.guardrail_stage.evaluate(ctx)
        if not should_continue:
            if persist:
                event = self.record_stage.execute(ctx, None, [])
                self._persist_and_learn(event, ctx)
            return ctx

        ctx = self.memory_stage.execute(ctx)
        ctx = self.knowledge_stage.execute(ctx)
        ctx = self.binder_stage.execute(ctx)
        ctx, belief, opinions = self.council_stage.execute(ctx)
        ctx = self.meta_stage.execute(ctx, belief)
        ctx = self.risk_target_stage.execute(ctx)
        ctx = self.decision_fusion.execute(ctx, belief)
        ctx = self.risk_gate_stage.execute(ctx)

        ctx.__dict__["_last_belief"] = belief
        ctx.__dict__["_last_opinions"] = opinions

        if persist:
            event = self.record_stage.execute(ctx, belief, opinions)
            self._persist_and_learn(event, ctx)
        return ctx

    def finalize(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        """Outcome set edildikten sonra tek kayit + learning."""
        belief = ctx.__dict__.get("_last_belief")
        opinions = ctx.__dict__.get("_last_opinions") or []
        event = self.record_stage.execute(ctx, belief, opinions)
        self._persist_and_learn(event, ctx)
        if ctx.outcome is not None:
            self.memory_engine.execute(ctx)
        return ctx

    def _persist_and_learn(
        self,
        event,
        ctx: CognitiveCycleContext,
    ) -> None:
        """Faz 250: kritik bulgu — bu metodun TEK çağıranı (services/
        orchestrator.py::finalize_proposal) ctx.outcome'ı gerçek bir
        pozisyon kapanışından değil, ForwardOutcome ile AYNI cycle'da
        geriye dönük hesaplanan bir n-bar pencereden dolduruyor — gerçek
        zaman hiç geçmiyor, gerçek stop/target mantığı hiç uygulanmıyor.
        Kullanıcı kararı: bu düşük kaliteli sinyal ne AgentMemory'yi
        (learning_loop.record) ne de ağırlıkları DOĞRUDAN (weight_optimizer.
        optimize + kaydetme) beslemeli — "kalitesiz hiçbir veri ile
        sistemi kirletmeyelim." Gerçek öğrenme artık SADECE
        services/position_closer.py (gerçek kapanışlar) ve
        backtest/real_historical_backtest.py (gerçek geçmiş veri,
        source="backtest") üzerinden gerçekleşiyor. RecordingStage zaten
        DecisionEvent'i ayrıca (bu metodun dışında) kalıcı hale getiriyor
        — bu metod artık kasıtlı olarak no-op."""
        return
