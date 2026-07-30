"""Memory Engine — çevrim sonu hafıza konsolidasyonu."""
from contracts.context import CognitiveCycleContext
from services.memory_consolidator import MemoryConsolidator


class MemoryEngine:
    def __init__(self, consolidator: MemoryConsolidator | None = None):
        self.consolidator = consolidator or MemoryConsolidator()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        # 1. Çevrimi Working Memory'ye kaydet
        self.consolidator.capture_cycle(ctx)
        # 2. Episodic Memory'ye yaz
        self.consolidator.commit_to_episodic(ctx)
        # 3. Yeterli veri varsa Semantic Memory'yi güncelle
        self.consolidator.consolidate_if_ready()
        # 4. Context'e hafıza metriklerini ekle
        ctx.cognition.relevant_knowledge.append({
            "type": "memory_stats",
            "data": {
                "working_items": len(self.consolidator.working.observations),
                "episodic_count": len(self.consolidator.episodic.episodes),
                "semantic_beliefs": len(self.consolidator.semantic.consolidated_beliefs),
            }
        })
        return ctx
