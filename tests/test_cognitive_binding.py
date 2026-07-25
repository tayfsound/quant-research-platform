"""UCEL Cognitive Binding testleri."""
from contracts.observation import Observation, ObservationType
from services.cognitive_binder import CognitiveBinder

def test_bind_observation_creates_ucel_expression():
    binder = CognitiveBinder()
    obs = Observation(type=ObservationType.INDICATOR, symbol="BTCUSDT", timeframe="4H", description="RSI oversold", data={"rsi": 25})
    binding = binder.bind_observation(obs)
    assert binding is not None
    assert binding.source_type == "observation"

def test_binding_evaluates_correctly():
    binder = CognitiveBinder()
    obs = Observation(type=ObservationType.INDICATOR, symbol="BTCUSDT", timeframe="4H", description="RSI normal", data={"rsi": 50})
    binding = binder.bind_observation(obs)
    assert binding.evaluate({"RSI": 50}) is False

def test_binding_to_knowledge():
    binder = CognitiveBinder()
    obs = Observation(type=ObservationType.INDICATOR, symbol="BTCUSDT", timeframe="4H", description="RSI oversold", data={"rsi": 25})
    binding = binder.bind_observation(obs)
    entry = binder.observation_to_knowledge(binding)
    assert entry.category.value == "observation"

def test_full_cognitive_cycle_with_ucel():
    from contracts.context import CognitiveCycleContext
    from services.cognitive_engine import CognitiveEngine
    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25, "ATR": 3.5}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    result = engine.run(ctx)
    assert result.decision.action is not None
    assert result.market.symbol == "BTCUSDT"
