"""Tam Bilişsel Döngü testi — pipeline."""
from uuid import uuid4

from contracts.context import CognitiveCycleContext
from services.cognitive_engine import CognitiveEngine


def test_full_cognitive_cycle_with_council():
    from contracts.contexts.risk import RiskLimitEntry
    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={
            # Gap #8 (MemoryEngine) kapandıktan sonra semantic recall gerçekten
            # çalışıyor — paylaşılan test DB'sinde biriken gürültülü geçmiş
            # (bu oturumun kendi test çalıştırmalarından) bu testin "net
            # bullish girdi -> pozitif güven" varsayımını bozabiliyordu. Her
            # zaman hiç geçmişi olmayan benzersiz bir sembol kullanarak
            # memory_confidence'ı nötr (0.5) varsayılanda tutuyoruz.
            "symbol": f"CYCLETEST{uuid4().hex[:8]}",
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
                "structure_phase": "accumulation",
                "break_of_structure": "bullish",
                "swing_structure": "higher_highs_higher_lows",
                "zscore": -2.2,
                "hurst_exponent": 0.35,
                "bid_ask_imbalance": 0.5,
                "spread_bps": 2.0,
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
def test_binder_stage_produces_belief_from_wisdom():
    """BinderStage wisdom itemlarini belief e cevirir (CognitiveBinder bound)."""
    from engines.cognitive_pipeline import BinderStage, KnowledgeStage
    from contracts.context import CognitiveCycleContext

    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.decision.proposed_direction = "LONG"

    ks = KnowledgeStage()
    ctx = ks.execute(ctx)

    bs = BinderStage()
    ctx = bs.execute(ctx)

    binder_beliefs = [k for k in ctx.cognition.relevant_knowledge if k.get("type") == "binder_belief"]
    assert len(binder_beliefs) > 0
    assert "data" in binder_beliefs[0]
    assert "direction" in binder_beliefs[0]["data"]
