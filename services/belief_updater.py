"""Belief Updater — yeni BeliefEngine ile."""
from contracts.context import CognitiveCycleContext
from contracts.outcome import DecisionEvaluation
from services.belief_engine import BeliefEngine
from contracts.agent import AgentOpinion, AgentDomain

class BeliefUpdater:
    def __init__(self, belief_engine: BeliefEngine | None = None):
        self.belief_engine = belief_engine or BeliefEngine()

    def update_from_outcome(self, ctx: CognitiveCycleContext, evaluation: DecisionEvaluation):
        memory_insights = [
            item for item in ctx.cognition.relevant_knowledge
            if item.get("type") == "memory_insight"
        ]
        if not memory_insights:
            return
        
        insight = memory_insights[-1]["data"]
        dominant = insight.get("dominant_direction", "NEUTRAL")
        
        # Yeni BeliefEngine ile sentezle (stub: tek agent görüşü olarak)
        opinion = AgentOpinion(
            domain=AgentDomain.TECHNICAL,
            direction=dominant,
            confidence=0.7,
        )
        self.belief_engine.synthesize([opinion])
