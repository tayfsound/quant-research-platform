"""Decision Engine — hafıza içgörüsünü kullanır."""
from contracts.context import CognitiveCycleContext

class DecisionEngine:
    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        # Hafıza içgörüsünü bul
        memory_items = [item for item in ctx.cognition.relevant_knowledge if item.get("type") == "memory_insight"]
        
        if memory_items and ctx.decision.proposed_direction:
            insight = memory_items[-1]["data"]
            # Yüksek güvenli hafıza içgörüsü varsa, önerilen yönü onayla veya geçersiz kıl
            if insight["confidence"] > 0.6:
                ctx.decision.final_direction = insight["dominant_direction"] if insight["dominant_direction"] != "NEUTRAL" else ctx.decision.proposed_direction
                ctx.decision.final_size = ctx.decision.proposed_size
            else:
                ctx.decision.final_direction = ctx.decision.proposed_direction
                ctx.decision.final_size = ctx.decision.proposed_size
        else:
            ctx.decision.final_direction = ctx.decision.proposed_direction
            ctx.decision.final_size = ctx.decision.proposed_size

        return ctx
