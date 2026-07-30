"""Decision Fusion — Expected Value ve Risk/Reward odaklı son karar aşaması."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.inner_critic import InnerCritic


class DecisionFusion:
    def __init__(self):
        self.critic = InnerCritic()

    def evaluate(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief | None = None,
    ) -> CognitiveCycleContext:
        confidence = ctx.decision.confidence or (belief.strength if belief else 0.0)
        win = ctx.decision.take_profit or 0.0
        loss = abs(ctx.decision.stop_loss or 0.0)
        ev = confidence * win - (1 - confidence) * loss

        if ev <= 0:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {"rejection": "Negative EV", "ev": round(ev, 6)},
            })
            return ctx

        if loss > 0 and win / loss < 0.5:
            ctx.decision.final_size *= 0.5
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {
                    "adjustment": "R/R too low, size halved",
                    "rr": round(win / loss, 6),
                },
            })

        return ctx
