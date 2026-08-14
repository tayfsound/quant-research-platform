"""Executive Layer testleri."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.decision_fusion import DecisionFusion
from services.inner_critic import InnerCritic
from services.salience_detector import SalienceDetector


def test_salience_low_score_returns_wait():
    detector = SalienceDetector(threshold=0.7)
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1}},
    )
    assert detector.should_act(ctx) is False
    assert detector.evaluate(ctx) < 0.7

def test_salience_high_score_triggers_action():
    detector = SalienceDetector(threshold=0.7)
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 22, "ATR": 4, "volume_ratio": 3}},
    )
    assert detector.should_act(ctx) is True

def test_critic_produces_output():
    """Critic herhangi bir çıktı üretmeli (risk_flags, challenges veya improvements)."""
    critic = InnerCritic()
    ctx = CognitiveCycleContext(
        market={"features": {"ATR": 5, "RSI": 15}},
        decision={"proposed_direction": "LONG", "proposed_size": 1.0},
    )
    result = critic.review(ctx)
    # En az bir anahtar dolu olmalı
    assert len(result.get("objections", [])) + len(result.get("risk_flags", [])) + len(result.get("improvements", [])) >= 1

def test_fusion_returns_action_type():
    fusion = DecisionFusion()
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50}},
        decision={"proposed_direction": "LONG", "proposed_size": 1.0},
    )
    result = fusion.evaluate(ctx, None)
    assert result.decision.action == ActionType.WAIT
