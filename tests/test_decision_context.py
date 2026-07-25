"""Decision Context Builder testleri — unit test."""
from contracts.context import CognitiveCycleContext
from services.decision_context_builder import DecisionContextBuilder

class FakeSearch:
    def find_similar_episodes(self, *args, **kwargs):
        return [
            {"decision": "LONG", "outcome": {"pnl": 100}},
            {"decision": "LONG", "outcome": {"pnl": -50}},
            {"decision": "SHORT", "outcome": {"pnl": 200}},
        ]

def test_enrich_adds_memory_insight():
    builder = DecisionContextBuilder()
    builder.search = FakeSearch()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25}},
    )
    enriched = builder.enrich(ctx)
    memory_items = [item for item in enriched.cognition.relevant_knowledge if item.get("type") == "memory_insight"]
    assert len(memory_items) == 1
    insight = memory_items[0]["data"]
    assert insight["similar_count"] == 3
    assert insight["dominant_direction"] == "LONG"

def test_enrich_empty_features():
    builder = DecisionContextBuilder()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {}},
    )
    enriched = builder.enrich(ctx)
    memory_items = [item for item in enriched.cognition.relevant_knowledge if item.get("type") == "memory_insight"]
    assert len(memory_items) == 0
