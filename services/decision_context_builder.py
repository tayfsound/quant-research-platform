"""Decision Context Builder — örneklem ağırlıklı confidence, düzeltilmiş avg_pnl."""
from services.semantic_search import SemanticSearch
from contracts.context import CognitiveCycleContext
from contracts.memory_context import MemoryInsight

class DecisionContextBuilder:
    def __init__(self):
        self.search = SemanticSearch()

    def enrich(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if not ctx.market.features:
            return ctx

        similar = self.search.find_similar_episodes(
            query_features=ctx.market.features,
            symbol=ctx.market.symbol,
            limit=20,
        )

        if not similar:
            return ctx

        pnls = []
        longs = shorts = 0
        for e in similar:
            outcome = e.get("outcome")
            if isinstance(outcome, dict):
                pnl = outcome.get("pnl", 0)
                if pnl is not None:
                    pnls.append(float(pnl))
            if e.get("decision") == "LONG":
                longs += 1
            elif e.get("decision") == "SHORT":
                shorts += 1

        total = len(similar)
        wins = sum(1 for p in pnls if p > 0)
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0

        if longs > shorts:
            dominant = "LONG"
        elif shorts > longs:
            dominant = "SHORT"
        else:
            dominant = "NEUTRAL"

        # Örneklem büyüklüğü ile ağırlıklandırılmış confidence
        raw_confidence = abs(wins / total - 0.5) * 2 if total > 0 else 0.0
        sample_weight = min(total / 50, 1.0)
        confidence = round(raw_confidence * sample_weight, 3)

        insight = MemoryInsight(
            similar_count=total,
            win_rate=round(wins / total, 3) if total > 0 else 0.0,
            average_pnl=round(avg_pnl, 2),
            dominant_direction=dominant,
            confidence=confidence,
        )

        ctx.cognition.relevant_knowledge.append({
            "type": "memory_insight",
            "data": insight.model_dump(),
        })

        return ctx
