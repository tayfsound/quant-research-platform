"""Cognitive Layer testleri — güncellenmiş."""
from contracts.context import CognitiveCycleContext
from services.cognitive_engine import CognitiveEngine


def test_cognitive_engine_runs():
    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    result = engine.run(ctx)
    assert result.decision.action is not None
