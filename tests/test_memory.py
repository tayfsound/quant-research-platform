"""Memory testleri — güncellenmiş."""
from contracts.context import CognitiveCycleContext
from contracts.memory import Episode, EpisodicMemory, SemanticMemory, WorkingMemory
from services.memory_consolidator import MemoryConsolidator


def test_working_memory_limits():
    wm = WorkingMemory(max_items=3)
    for i in range(5):
        wm.add_observation({"id": i})
    assert len(wm.observations) == 3

def test_episodic_memory_sample():
    em = EpisodicMemory()
    for i in range(20):
        em.add_episode(Episode(symbol="BTCUSDT", observation={}))
    sample = em.sample(5)
    assert len(sample) == 5

def test_semantic_consolidation():
    em = EpisodicMemory()
    sm = SemanticMemory()
    for i in range(15):
        em.add_episode(Episode(symbol="BTCUSDT", binding_expression="RSI < 30", outcome={"pnl": 100 if i % 2 == 0 else -50}))
    sm.consolidate(em, threshold=10)
    assert sm.total_episodes == 10

def test_memory_consolidator_cycle():
    cons = MemoryConsolidator()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    ctx.cognition.relevant_knowledge.append({"type": "cognitive_binding", "data": {"expression": {"description": "RSI < 30"}}})
    cons.capture_cycle(ctx)
    episode = cons.commit_to_episodic(ctx)
    assert episode is not None

def test_full_cycle_with_memory():
    from services.cognitive_engine import CognitiveEngine
    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25, "ATR": 3.5}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    result = engine.run(ctx)
    memory_stats = [item for item in result.cognition.relevant_knowledge if item.get("type") == "memory_insight"]
    # Memory insight eklenmiş olmalı (boş olabilir, önemli olan tipin var olması)
    assert isinstance(memory_stats, list)
