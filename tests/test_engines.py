"""Engine testleri — güncellenmiş."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.cognitive_engine import CognitiveEngine

def test_cognitive_cycle():
    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25, "ATR": 3.5}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    result = engine.run(ctx)
    # Yeni mimaride WAIT/REDUCE/ACT dönebilir
    assert result.decision.action in (
        ActionType.WAIT, ActionType.REDUCE,
        ActionType.ENTER_LONG, ActionType.ENTER_SHORT,
    )
