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

def test_strong_council_consensus_alone_can_reach_act_without_any_memory():
    """Faz 203: kritik bulgu — belief_strength (Council'in bu cycle'daki
    GERÇEK, ağırlıklı konsensüs gücü) daha önce hiç kullanılmıyordu; hafıza
    yoksa confidence sabit 0.5'e düşüp sadece aşağı inebiliyordu, 9 ajan
    bile birleşse ACT eşiğine ulaşamıyordu. Artık hafıza hiç yokken bile
    güçlü bir belief_strength tek başına ACT'i tetikleyebilmeli."""
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()  # hiç memory_insight yok

    result = meta.evaluate_confidence(
        ctx, {"risk_flags": []}, {"conflict_level": 0.0}, belief_strength=0.85,
    )

    assert result["confidence"] >= 0.7
    assert result["decision"] == "ACT"


def test_weak_council_consensus_without_memory_still_waits():
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()

    result = meta.evaluate_confidence(
        ctx, {"risk_flags": []}, {"conflict_level": 0.0}, belief_strength=0.2,
    )

    assert result["decision"] == "WAIT"


def test_high_risk_penalty_still_overrides_a_strong_belief_strength():
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()

    result = meta.evaluate_confidence(
        ctx,
        {"risk_flags": ["direction_conflict", "high_volatility"]},
        {"conflict_level": 0.8},
        belief_strength=0.9,
    )

    assert result["decision"] == "WAIT"


def test_agreeing_timeframe_belief_boosts_confidence():
    """Faz 268c — Multi-Timeframe Cascade: birden fazla zaman diliminin
    AYNI yönü teyit etmesi, tek başına belief_strength'ten daha güçlü bir
    konviksiyon üretmeli (rapor: "1m LONG + 15m LONG + 1h LONG, yalnızca
    1m LONG'dan çok daha güçlü bir konviksiyon demektir")."""
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()
    ctx.cognition.relevant_knowledge.append({
        "type": "timeframe_belief",
        "data": {"combined_direction": "LONG", "combined_confidence": 0.9},
    })

    result = meta.evaluate_confidence(
        ctx, {"risk_flags": []}, {"conflict_level": 0.0},
        belief_strength=0.5, belief_direction="LONG",
    )

    assert result["confidence"] > 0.5  # zaman dilimi teyidi confidence'ı yukarı çekti


def test_disagreeing_timeframe_belief_reduces_confidence():
    """Üst zaman dilimleri birincil yönle ÇELİŞİYORSA (ör. 1m LONG ama
    15m/1h SHORT diyor) bu bir uyarı sinyali — sessizce yok sayılmamalı,
    confidence aşağı çekilmeli (raporun hedeflediği "yanlış pozitifleri
    azaltma" etkisi)."""
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()
    ctx.cognition.relevant_knowledge.append({
        "type": "timeframe_belief",
        "data": {"combined_direction": "SHORT", "combined_confidence": 0.9},
    })

    result = meta.evaluate_confidence(
        ctx, {"risk_flags": []}, {"conflict_level": 0.0},
        belief_strength=0.6, belief_direction="LONG",
    )

    assert result["confidence"] < 0.6  # çelişki confidence'ı aşağı çekti


def test_no_timeframe_belief_present_is_a_no_op():
    """Multi-Timeframe Cascade kapalıyken (varsayılan) hiç timeframe_belief
    enjekte edilmez — bu durumda davranış eskisiyle birebir aynı kalmalı."""
    meta = Metacognition(act_threshold=0.7, reduce_threshold=0.4)
    ctx = CognitiveCycleContext()

    result = meta.evaluate_confidence(
        ctx, {"risk_flags": []}, {"conflict_level": 0.0},
        belief_strength=0.5, belief_direction="LONG",
    )

    assert result["confidence"] == 0.5


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
