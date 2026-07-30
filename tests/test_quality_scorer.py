"""Quality Scorer testleri."""
from contracts.decision_event import DecisionEvent
from ml.training.quality_scorer import SampleQualityScorer


def test_quality_scoring():
    scorer = SampleQualityScorer()

    # Yüksek kaliteli örnek
    event_high = DecisionEvent(
        symbol="BTCUSDT",
        market_snapshot={"features": {"RSI": 30}},
        agent_opinions=[
            {"confidence": 0.9, "direction": "LONG"},
            {"confidence": 0.1, "direction": "SHORT"}
        ],
        confidence=0.8,
        outcome={"pnl": 12.0, "win": True} # Yüksek PnL
    )

    scores_high = scorer.score_sample(event_high)
    assert scores_high["completeness_score"] == 1.0
    assert scores_high["final_quality_score"] > 0.5

    # Düşük kaliteli örnek (eksik veri)
    event_low = DecisionEvent(
        symbol="ETHUSDT",
        market_snapshot={}, # Eksik pazar verisi
        agent_opinions=[], # Eksik ajan görüşü
        outcome=None # Eksik sonuç
    )

    scores_low = scorer.score_sample(event_low)
    assert scores_low["completeness_score"] < 0.5
    assert scores_low["final_quality_score"] < 0.3
