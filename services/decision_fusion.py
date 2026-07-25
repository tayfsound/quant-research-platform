"""Decision Fusion — ActionType güncel."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.salience_detector import SalienceDetector
from services.inner_critic import InnerCritic

class DecisionFusion:
    def __init__(self):
        self.salience = SalienceDetector(threshold=0.7)
        self.critic = InnerCritic()

    def evaluate(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        importance = self.salience.evaluate(ctx)

        if not self.salience.should_act(ctx):
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.cognition.relevant_knowledge.append({
                "type": "executive_decision",
                "data": {"action": "WAIT", "reason": f"Importance score {importance:.2f} < threshold"}
            })
            return ctx

        criticism = self.critic.review(ctx)
        risk_flags = criticism.get("risk_flags", [])
        
        if len(risk_flags) >= 2:
            ctx.decision.action = ActionType.REDUCE
            ctx.decision.final_size = ctx.decision.proposed_size * 0.5
        elif len(risk_flags) == 1:
            ctx.decision.action = ActionType.REDUCE
            ctx.decision.final_size = ctx.decision.proposed_size * 0.75

        if "direction_conflict" in risk_flags:
            ctx.decision.action = ActionType.RECONSIDER

        ctx.cognition.relevant_knowledge.append({
            "type": "executive_decision",
            "data": {
                "action": ctx.decision.action.value,
                "importance": importance,
                "criticism": criticism,
            }
        })

        return ctx
