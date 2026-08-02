"""Cognitive Pipeline — stage zinciri."""

from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from contracts.contexts.risk import RiskReason


class GuardrailStage:
    """Erken risk guardrail — hash verify + limit var mı."""

    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        limits = ctx.risk.limits
        if not limits or not limits.verify(ctx.risk.secret):
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [
                RiskReason(
                    code="GUARDRAIL_FAIL",
                    message="Risk limits missing or unverified",
                    severity="critical",
                )
            ]
        return ctx


class MemoryStage:
    """Working memory — anlık bağlam."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return ctx


class KnowledgeStage:
    """Knowledge retrieval — semantic memory'den ilgili bilgiyi çek."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return ctx


class BinderStage:
    """Knowledge → Belief dönüşümü — sadece wisdom tipi."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        knowledge = ctx.cognition.relevant_knowledge
        binder_beliefs = []
        for item in knowledge:
            if item.get("type") == "wisdom":
                from contracts.belief import Belief
                belief = Belief(
                    direction=item.get("direction", "NEUTRAL"),
                    strength=item.get("confidence", 0.5),
                    uncertainty=1.0 - item.get("confidence", 0.5),
                    evidence_paths=[item.get("principle", "")],
                    assumptions=[item.get("category", "")],
                    total_opinions=item.get("validation_count", 0),
                )
                binder_beliefs.append({"type": "binder_belief", "belief": belief})
        ctx.cognition.relevant_knowledge.extend(binder_beliefs)
        return ctx


class CouncilStage:
    """Agent council — çoklu agent görüş birliği."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return ctx


class MetaStage:
    """Meta cognition — council çıktısını değerlendir."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return ctx


class DecisionFusionStage:
    """Karar füzyonu — council çıktısını birleştir."""

    def execute(self, ctx: CognitiveCycleContext, belief) -> CognitiveCycleContext:
        return ctx


class RiskGateStage:
    """Post-fusion risk gate — evaluates final_size against signed limits."""

    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def execute(self, ctx):
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

        if reasons:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
        else:
            ctx.risk.evaluation.verdict = "approved"

        return ctx


class RecordingStage:
    """Decision + belief persistence — DB'ye kayıt."""

    def __init__(self):
        from services.decision_recorder import DecisionRecorder
        self.recorder = DecisionRecorder()

    def execute(self, ctx, belief, agent_opinions):
        from contracts.decision_event import DecisionEvent
        from database.session_factory import SessionFactory
        from database.repositories.experiment_registry_repository import ExperimentRegistryRepository
        from contracts.experiment_registry import ExperimentRegistry

        event = DecisionEvent(
            symbol=ctx.market.symbol,
            proposed_direction=ctx.decision.proposed_direction,
            confidence=ctx.decision.confidence,
            final_size=ctx.decision.final_size,
            action=ctx.decision.action,
            agent_opinions=agent_opinions,
            risk_evaluation=ctx.risk.evaluation,
            market_snapshot={"raw_snapshot": ctx.market.__dict__},
        )

        self.recorder.record(event)

        if belief is not None:
            from services.memory_service import MemoryService
            MemoryService().store_belief(belief)

        try:
            exp = ExperimentRegistry(
                git_sha=ExperimentRegistry.get_git_sha(),
                decision_ids=[str(event.id)] if event.id else [],
            )
            with SessionFactory.get_session() as session:
                ExperimentRegistryRepository(session).save(exp)
        except Exception:
            pass

        return event
