"""Knowledge Builder — önce topla, sonra ekle (sonsuz döngü riski yok)."""
from contracts.cognitive_binding import CognitiveBinding
from contracts.context import CognitiveCycleContext
from services.cognitive_binder import CognitiveBinder


class KnowledgeBuilder:
    def __init__(self):
        self.binder = CognitiveBinder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        bindings = [item for item in ctx.cognition.relevant_knowledge if item.get("type") == "cognitive_binding"]
        for item in bindings:
            binding = CognitiveBinding(**item["data"]) if isinstance(item["data"], dict) else item["data"]
            entry = self.binder.observation_to_knowledge(binding)
            ctx.cognition.relevant_knowledge.append({"type": "knowledge", "data": entry.model_dump()})
        return ctx
