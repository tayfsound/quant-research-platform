"""BinderStage processes only wisdom-type knowledge items."""
from contracts.context import CognitiveCycleContext


def test_only_wisdom_produces_binder_belief():
    from engines.cognitive_pipeline import BinderStage
    stage = BinderStage()
    ctx = CognitiveCycleContext()
    ctx.cognition.relevant_knowledge = [
        {"type": "wisdom", "category": "momentum", "principle": "RSI oversold", "confidence": 0.8, "validation_count": 3},
        {"type": "observation", "data": {"rsi": 25}},
        {"type": "debate_result", "data": {"winner": "technical"}},
    ]
    ctx = stage.execute(ctx)
    binder_beliefs = [k for k in ctx.cognition.relevant_knowledge if k.get("type") == "binder_belief"]
    assert len(binder_beliefs) == 1
