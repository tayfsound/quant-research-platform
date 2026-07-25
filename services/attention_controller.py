"""Attention Controller — yeniden düşünme döngüsü, hipotez invalidasyonu."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType

class AttentionController:
    def __init__(self, max_reconsider_loops: int = 2):
        self.loop_count = 0
        self.max_loops = max_reconsider_loops

    def should_reconsider(self, contradiction: dict) -> bool:
        return (
            contradiction.get("recommendation") == "RECONSIDER"
            and self.loop_count < self.max_loops
        )

    def reconsider(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        """
        Gerçek refleksiyon: hipotezi geçersiz kıl, yeniden düşün.
        Sadece pozisyon azaltmaz — düşünceyi yeniden değerlendirir.
        """
        self.loop_count += 1
        ctx.decision.reconsideration_count += 1
        
        # Mevcut hipotezi geçersiz kıl — sistem yeniden düşünsün
        ctx.decision.proposed_direction = ""
        ctx.decision.action = ActionType.RECONSIDER
        
        ctx.cognition.relevant_knowledge.append({
            "type": "reconsideration",
            "data": {
                "loop": self.loop_count,
                "reason": "Contradiction detected — re-evaluating hypothesis",
            }
        })
        return ctx

    def reset(self):
        self.loop_count = 0
