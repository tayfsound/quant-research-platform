"""Feature Extractor testleri."""
import pytest
from ml.training.feature_extractor import TrainingFeatureExtractor
from contracts.decision_event import DecisionEvent

def test_feature_extraction():
    extractor = TrainingFeatureExtractor()
    
    event = DecisionEvent(
        symbol="BTCUSDT",
        market_snapshot={
            "features": {"RSI": 25, "ATR": 2.5} # Oversold
        },
        agent_opinions=[
            {"direction": "LONG", "confidence": 0.8, "evidence_strength": 0.7},
            {"direction": "SHORT", "confidence": 0.4, "evidence_strength": 0.3}
        ],
        belief_state={
            "strength": 0.9,
            "uncertainty": 0.1,
            "entropy": 0.2,
            "cluster_disagreement": 0.5
        },
        confidence=0.85,
        decision_latency_ms=10.5,
        outcome={"pnl": 5.5, "win": True}
    )
    
    features = extractor.extract_features(event)
    
    # Mevcut kontroller
    assert features["market_RSI"] == 25
    assert features["agent_avg_confidence"] == pytest.approx(0.6)
    assert features["belief_strength"] == 0.9
    
    # FEATURE ENGINEERING KONTROLLERİ
    
    # Polarization: 1 pos, 1 neg -> min(1,1)/max(1,2) = 0.5
    assert features["agent_polarization"] == 0.5
    
    # Weighted Consensus: (1*0.8 + -1*0.4) / (0.8+0.4) = 0.4 / 1.2 = 0.333
    assert features["agent_weighted_consensus"] == pytest.approx(0.333, rel=1e-2)
    
    # Oversold Alignment: RSI 25 < 30 -> belief_strength (0.9)
    assert features["belief_oversold_alignment"] == 0.9
    
    # Confidence Gap: 0.85 - 0.6 = 0.25
    assert features["confidence_gap"] == pytest.approx(0.25)
    
    # Label kontrolleri
    label_pnl = extractor.extract_label(event, "pnl")
    assert label_pnl == 5.5
    
    label_win = extractor.extract_label(event, "win")
    assert label_win == 1
