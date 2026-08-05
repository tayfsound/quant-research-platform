"""Cognitive Pipeline Aşamaları — opinions akışı + Debate hafızası + RecordingStage."""
from contracts.contexts.decision import ActionType
from contracts.contexts.risk import RiskReason

from agents.registry import AgentRegistry
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.decision_event import DecisionEvent
from contracts.experiment_registry import ExperimentRegistry
from services.context_adapter import ContextAdapter
from services.council_orchestrator import CouncilOrchestrator
from services.decision_context_builder import DecisionContextBuilder
from services.decision_fusion import DecisionFusion
from services.decision_recorder import DecisionRecorder
from services.knowledge_base import KnowledgeBase
from services.metacognition import Metacognition


class MemoryStage:
    def __init__(self):
        self.context_builder = DecisionContextBuilder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return self.context_builder.enrich(ctx)


class KnowledgeStage:
    def __init__(self, knowledge_base: KnowledgeBase | None = None):
        self.knowledge_base = knowledge_base or KnowledgeBase()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        relevant = self.knowledge_base.query_relevant(
            ctx.market.model_dump(),
            ctx.decision.model_dump(),
        )
        ctx.cognition.relevant_knowledge.extend(relevant)
        return ctx


class CouncilStage:
    def __init__(self, registry: AgentRegistry, pinned_weight_snapshot_id=None):
        self.registry = registry
        self.adapter = ContextAdapter()
        self.orchestrator = CouncilOrchestrator(
            registry, pinned_weight_snapshot_id=pinned_weight_snapshot_id
        )
        self.knowledge_base = KnowledgeBase()

    def execute(self, ctx: CognitiveCycleContext) -> tuple[CognitiveCycleContext, Belief, list[AgentOpinion]]:
        wisdom = self.knowledge_base.query_relevant(
            ctx.market.model_dump(),
            ctx.decision.model_dump(),
        )
        for w in wisdom:
            ctx.cognition.relevant_knowledge.append(w)

        contexts = {
            AgentDomain.MACRO: self.adapter.to_macro(ctx),
            AgentDomain.SENTIMENT: self.adapter.to_sentiment(ctx),
            AgentDomain.ONCHAIN: self.adapter.to_onchain(ctx),
            AgentDomain.TECHNICAL: self.adapter.to_technical(ctx),
            AgentDomain.PATTERN: self.adapter.to_pattern(ctx),
            AgentDomain.QUANT: self.adapter.to_quant(ctx),
            AgentDomain.ORDER_FLOW: self.adapter.to_order_flow(ctx),
            AgentDomain.TIME: self.adapter.to_time(ctx),
            AgentDomain.EPISTEMOLOGY: self.adapter.to_epistemology(ctx),
        }

        belief, opinions = self.orchestrator.deliberate(contexts)

        ctx.cognition.relevant_knowledge.append({
            "type": "weight_snapshot",
            "data": {
                "id": str(self.orchestrator.active_weight_snapshot_id)
                if self.orchestrator.active_weight_snapshot_id
                else None
            },
        })

        ctx.cognition.relevant_knowledge.append({
            "type": "council_belief",
            "data": belief.model_dump(),
        })

        # Debate katmanı çıktısını bilişsel hafızaya kaydet
        if self.orchestrator.last_debate_result:
            ctx.cognition.relevant_knowledge.append({
                "type": "debate_result",
                "data": self.orchestrator.last_debate_result.model_dump(),
            })

        return ctx, belief, opinions


class MetaStage:
    def __init__(self):
        self.metacognition = Metacognition()

    def execute(self, ctx: CognitiveCycleContext, belief: Belief) -> CognitiveCycleContext:
        conflict_level = max(
            belief.cluster_disagreement,
            belief.crowding_penalty,
            belief.uncertainty,
        )

        criticism = {"risk_flags": []}

        if belief.cluster_balance < 0.3:
            criticism["risk_flags"].append("low_cluster_balance")

        if belief.crowding_penalty > 0.5:
            criticism["risk_flags"].append("high_crowding")

        meta = self.metacognition.evaluate_confidence(
            ctx,
            criticism,
            {"conflict_level": conflict_level},
        )

        ctx.decision.confidence = meta["confidence"]
        ctx.decision.uncertainty = meta["uncertainty"]
        if meta["decision"] == "WAIT":
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0

        elif meta["decision"] == "REDUCE":
            ctx.decision.action = ActionType.REDUCE
            ctx.decision.final_size = ctx.decision.proposed_size * meta["confidence"]

        else:
            if belief.direction == "LONG":
                ctx.decision.action = ActionType.ENTER_LONG
            elif belief.direction == "SHORT":
                ctx.decision.action = ActionType.ENTER_SHORT
            else:
                ctx.decision.action = ActionType.WAIT

        ctx.decision.proposed_direction = belief.direction

        return ctx


class DecisionFusionStage:
    def __init__(self):
        self.fusion = DecisionFusion()

    def execute(self, ctx: CognitiveCycleContext, belief: Belief) -> CognitiveCycleContext:
        return self.fusion.evaluate(ctx, belief)


class BinderStage:
    """Knowledge -> CognitiveBinding -> Belief (P0-5 bind)."""
    def __init__(self):
        from services.cognitive_binder import CognitiveBinder
        self.binder = CognitiveBinder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        for item in ctx.cognition.relevant_knowledge:
            if item.get("type") == "wisdom":
                from contracts.expression import Expression, Constant
                from contracts.cognitive_binding import CognitiveBinding
                expr = Expression(
                    name=item.get("category", "unknown"),
                    description=item.get("principle", ""),
                    root=Constant(value=item.get("confidence", 0.5)),
                )
                binding = CognitiveBinding(
                    source_type="knowledge_base",
                    expression=expr,
                    confidence=item.get("confidence", 0.5),
                    evidence_count=item.get("validation_count", 0),
                )
                belief = self.binder.knowledge_to_belief(binding)
                ctx.cognition.relevant_knowledge.append({
                    "type": "binder_belief",
                    "data": belief.model_dump(),
                })
        return ctx



class RecordingStage:
    def __init__(self):
        self.recorder = DecisionRecorder()

    def execute(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief,
        opinions: list[AgentOpinion],
    ) -> DecisionEvent:

        debate_result = None
        weight_snapshot_id = None

        if hasattr(ctx, "cognition"):
            for item in reversed(ctx.cognition.relevant_knowledge):
                if item.get("type") == "debate_result":
                    debate_result = item.get("data")

                if item.get("type") == "weight_snapshot":
                    weight_snapshot_id = item.get("data", {}).get("id")

                if debate_result and weight_snapshot_id:
                    break

        event = self.recorder.record(
            ctx,
            opinions,
            belief,
            debate_result,
            weight_snapshot_id,
        )

        from observability.metrics import decisions_total
        decisions_total.labels(
            symbol=ctx.market.symbol or "unknown",
            action=str(getattr(ctx.decision, "action", "") or event.final_action or "WAIT"),
        ).inc()

        ctx.cognition.relevant_knowledge.append({
            "type": "decision_event",
            "data": event.model_dump(),
        })

        # Belief persistence -- pipeline'dan DB'ye (P0-6)
        if belief is not None:
            from services.memory_service import MemoryService
            MemoryService().store_belief(belief)

        # ExperimentRegistry log (Faz 159)
        try:
            from contracts.experiment_registry import ExperimentRegistry
            from database.session_factory import SessionFactory
            from database.repositories.experiment_registry_repository import ExperimentRegistryRepository
            exp = ExperimentRegistry(
                git_sha=ExperimentRegistry.get_git_sha(),
                decision_ids=[str(event.id)] if event.id else [],
            )
            with SessionFactory.get_session() as session:
                ExperimentRegistryRepository(session).save(exp)
        except Exception:
            pass

        return event


class RiskGateStage:
    """Post-fusion risk gate — evaluates final_size against signed limits."""

    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def execute(self, ctx):
        # Faz 188: test modunda hem ön hem son risk kapısı devre dışı.
        if ctx.risk.trading_mode == "test":
            ctx.risk.evaluation.verdict = "approved"
            return ctx

        limits = ctx.risk.limits
        final_size = getattr(ctx.decision, "final_size", 0.0)
        reasons = []

        max_size = limits.get("max_position_size")
        if max_size and final_size > max_size.value:
            reasons.append(RiskReason(
                code="POST_FUSION_SIZE_EXCEEDED",
                message="Final size " + str(final_size) + " > limit " + str(max_size.value),
                severity="critical",
            ))

        max_dd = limits.get("max_drawdown")
        if max_dd and ctx.risk.current_drawdown >= max_dd.value:
            reasons.append(RiskReason(
                code="MAX_DRAWDOWN",
                message="Drawdown exceeded",
                severity="critical",
            ))

        max_lev = limits.get("max_leverage")
        if max_lev and getattr(ctx.risk, "current_leverage", 0) > max_lev.value:
            reasons.append(RiskReason(
                code="MAX_LEVERAGE_EXCEEDED",
                message="Leverage exceeded",
                severity="critical",
            ))

        daily_loss = limits.get("daily_loss_limit")
        if daily_loss and getattr(ctx.risk, "daily_pnl", 0) <= -daily_loss.value:
            reasons.append(RiskReason(
                code="DAILY_LOSS_LIMIT",
                message="Daily loss limit exceeded",
                severity="critical",
            ))

        if ctx.risk.max_concurrent_positions is not None and ctx.risk.open_position_count >= ctx.risk.max_concurrent_positions:
            reasons.append(RiskReason(
                code="MAX_CONCURRENT_POSITIONS",
                message=f"{ctx.risk.open_position_count} open >= limit {ctx.risk.max_concurrent_positions}",
                severity="critical",
            ))

        if ctx.risk.max_capital_pct is not None and ctx.risk.capital_used_pct >= ctx.risk.max_capital_pct:
            reasons.append(RiskReason(
                code="MAX_CAPITAL_PCT",
                message=f"{ctx.risk.capital_used_pct:.1%} used >= limit {ctx.risk.max_capital_pct:.1%}",
                severity="critical",
            ))

        if reasons:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
        else:
            ctx.risk.evaluation.verdict = "approved"

        return ctx
