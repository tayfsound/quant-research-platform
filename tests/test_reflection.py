"""Reflection Engine testleri."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.attention_controller import AttentionController
from services.contradiction_detector import ContradictionDetector


def test_contradiction_low_conflict_proceed():
    detector = ContradictionDetector()
    result = detector.analyze(
        CognitiveCycleContext(),
        {"challenges": [], "risk_flags": [], "improvements": []}
    )
    assert result["recommendation"] == "PROCEED"
    assert result["conflict_level"] == 0.0

def test_contradiction_high_conflict_reconsider():
    detector = ContradictionDetector()
    result = detector.analyze(
        CognitiveCycleContext(),
        {
            "challenges": ["risk1", "risk2", "risk3"],
            "risk_flags": ["direction_conflict"],
            "improvements": [],
        }
    )
    assert result["recommendation"] == "RECONSIDER"
    assert result["conflict_level"] > 0.6

def test_attention_reconsider_invalidates_hypothesis():
    """Yeni davranış: reconsider hipotezi geçersiz kılar, RECONSIDER action'ı belirler."""
    controller = AttentionController(max_reconsider_loops=2)
    ctx = CognitiveCycleContext(
        decision={"proposed_direction": "LONG", "proposed_size": 1.0}
    )
    ctx = controller.reconsider(ctx)
    assert ctx.decision.action == ActionType.RECONSIDER
    assert ctx.decision.proposed_direction == ""
    assert ctx.decision.reconsideration_count == 1
