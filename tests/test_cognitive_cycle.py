"""Tam Bilişsel Döngü testi — pipeline."""
from contracts.context import CognitiveCycleContext
from services.cognitive_engine import CognitiveEngine


def test_full_cognitive_cycle_with_council():
    from contracts.contexts.risk import RiskLimitEntry
    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={
            "symbol": "BTCUSDT",
            "timeframe": "4H",
            "features": {"RSI": 35.0},
            "raw_snapshot": {
                "inflation_trend": "falling",
                "central_bank_bias": "dovish",
                "fear_greed_index": 25.0,
                "social_media_sentiment": -0.4,
                "positioning": "short_bias",
                "exchange_outflow_24h": 500_000_000,
                "whale_accumulation": True,
                "trend": "bullish",
                "momentum": "strengthening",
                "market_structure": "higher_highs",
                "volume_confirmation": True,
            }
        },
        decision={"proposed_size": 0.5},
        risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0)}},
    )

    result = engine.run(ctx)

    assert result.decision.action is not None
    assert result.decision.confidence > 0
    assert result.decision.proposed_direction in ("LONG", "SHORT", "WAIT")
    assert result.risk.evaluation.verdict in ("approved", "rejected")

    belief_items = [
        item for item in result.cognition.relevant_knowledge
        if item.get("type") == "council_belief"
    ]
    assert len(belief_items) == 1
