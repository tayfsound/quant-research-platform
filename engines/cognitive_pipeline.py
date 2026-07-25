"""Cognitive Pipeline Aşamaları — opinions akışı + Debate hafızası + RecordingStage."""
from contracts.context import CognitiveCycleContext
from contracts.belief import Belief
from contracts.agent import AgentOpinion, AgentDomain
from services.context_adapter import ContextAdapter
from agents.registry import AgentRegistry
from services.council_orchestrator import CouncilOrchestrator
from services.decision_context_builder import DecisionContextBuilder
from services.metacognition import Metacognition
from services.risk_gate import RiskGate
from services.decision_recorder import DecisionRecorder


class MemoryStage:
    def __init__(self):
        self.context_builder = DecisionContextBuilder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return self.context_builder.enrich(ctx)


class CouncilStage:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.adapter = ContextAdapter()
        self.orchestrator = CouncilOrchestrator(registry)

    def execute(self, ctx: CognitiveCycleContext) -> tuple[CognitiveCycleContext, Belief, list[AgentOpinion]]:
        contexts = {
            AgentDomain.MACRO: self.adapter.to_macro(ctx),
            AgentDomain.SENTIMENT: self.adapter.to_sentiment(ctx),
            AgentDomain.ONCHAIN: self.adapter.to_onchain(ctx),
            AgentDomain.TECHNICAL: self.adapter.to_technical(ctx),
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

        from contracts.contexts.decision import ActionType

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


class RiskStage:
    def __init__(self):
        self.risk_gate = RiskGate()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return self.risk_gate.evaluate(ctx)


class RecordingStage:
    def __init__(self):
        self.recorder = DecisionRecorder()

    def execute(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief,
        opinions: list[AgentOpinion],
    ) -> CognitiveCycleContext:

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

        ctx.cognition.relevant_knowledge.append({
            "type": "decision_event",
            "data": event.model_dump(),
        })

        return ctx
