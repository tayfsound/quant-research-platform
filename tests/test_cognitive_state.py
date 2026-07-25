"""Cognitive State Model testleri."""
from contracts.contexts.decision import ActionType, DecisionReason, Decision

def test_action_types():
    assert ActionType.WAIT == "WAIT"
    assert ActionType.ENTER_LONG == "ENTER_LONG"
    assert ActionType.REDUCE == "REDUCE"

def test_decision_reasons():
    assert DecisionReason.NO_SIGNAL == "NO_SIGNAL"
    assert DecisionReason.INSUFFICIENT_DATA == "INSUFFICIENT_DATA"
    assert DecisionReason.MEMORY_SUPPORTED == "MEMORY_SUPPORTED"

def test_decision_model():
    d = Decision(
        proposed_direction="LONG",
        proposed_size=1.0,
        action=ActionType.ENTER_LONG,
        reason=DecisionReason.MEMORY_SUPPORTED,
        confidence=0.85,
        uncertainty=0.15,
    )
    assert d.action == ActionType.ENTER_LONG
    assert d.confidence == 0.85
