"""Metacognition testleri — güncellenmiş."""
from contracts.context import CognitiveCycleContext
from services.metacognition import Metacognition

def test_high_confidence_act():
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()
    ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"confidence": 0.9}
    })
    result = meta.evaluate_confidence(ctx, {"risk_flags": []}, {"conflict_level": 0.0})
    assert result["confidence"] > 0.7
    assert result["decision"] == "ACT"

def test_moderate_confidence_reduce():
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()
    ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"confidence": 0.55}
    })
    result = meta.evaluate_confidence(ctx, {"risk_flags": []}, {"conflict_level": 0.1})
    assert result["decision"] == "REDUCE"

def test_low_confidence_wait():
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()
    ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"confidence": 0.2}
    })
    result = meta.evaluate_confidence(
        ctx,
        {"risk_flags": ["direction_conflict", "high_volatility"]},
        {"conflict_level": 0.8},
    )
    assert result["decision"] == "WAIT"

def test_no_memory_is_neutral():
    """Hiç hafıza yoksa memory_confidence 0.5 olmalı, sistem çalışabilmeli."""
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()
    result = meta.evaluate_confidence(ctx, {"risk_flags": []}, {"conflict_level": 0.0})
    assert result["confidence"] == 0.5  # nötr
    assert result["decision"] == "REDUCE"

def test_track_record():
    meta = Metacognition()
    meta.history = [
        {"confidence": 0.8, "was_correct": True},
        {"confidence": 0.6, "was_correct": False},
        {"confidence": 0.9, "was_correct": True},
    ]
    record = meta.get_track_record()
    assert record["total"] == 3
    assert abs(record["accuracy"] - 2/3) < 0.001
