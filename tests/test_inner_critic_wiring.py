"""Faz 268-sonrası — kritik bulgu (üçüncü taraf mimari incelemesi + gerçek
kod doğrulaması): InnerCritic, DecisionFusion.__init__'te instantiate
ediliyordu ama .review() hiç çağrılmıyordu — ürettiği risk_flags/
objections tamamen ölü koddu. Bu testler, artık review()'un çıktısının
(confidence_multiplier/size_multiplier) DecisionFusion.evaluate() içinde
GERÇEKTEN confidence/final_size'ı etkilediğini doğruluyor."""
from contracts.context import CognitiveCycleContext
from services.decision_fusion import DecisionFusion
from services.inner_critic import InnerCritic


def test_review_returns_neutral_multipliers_when_nothing_flagged():
    critic = InnerCritic()
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision={"proposed_direction": "LONG"},
    )
    result = critic.review(ctx)
    assert result["confidence_multiplier"] == 1.0
    assert result["size_multiplier"] == 1.0


def test_review_reduces_size_multiplier_on_high_volatility():
    critic = InnerCritic()
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 5, "volume_ratio": 1}},
        decision={"proposed_direction": "LONG"},
    )
    result = critic.review(ctx)
    assert result["size_multiplier"] == 0.7
    assert "high_volatility" in result["risk_flags"]


def test_review_reduces_confidence_multiplier_on_memory_direction_conflict():
    critic = InnerCritic()
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision={"proposed_direction": "LONG"},
    )
    ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"dominant_direction": "SHORT", "confidence": 0.8},
    })
    result = critic.review(ctx)
    assert "direction_conflict" in result["risk_flags"]
    # confidence=0.8 olan güçlü bir çelişen örüntü -> anlamlı ama asla
    # %50'den fazla olmayan bir indirim (bkz. inner_critic.py notu).
    assert 0.5 <= result["confidence_multiplier"] < 1.0


def test_review_barely_discounts_confidence_when_conflicting_memory_is_weak():
    critic = InnerCritic()
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision={"proposed_direction": "LONG"},
    )
    ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"dominant_direction": "SHORT", "confidence": 0.05},
    })
    result = critic.review(ctx)
    assert result["confidence_multiplier"] > 0.95


def test_review_does_not_flag_conflict_when_no_memory_insight_present():
    critic = InnerCritic()
    ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision={"proposed_direction": "LONG"},
    )
    result = critic.review(ctx)
    assert "direction_conflict" not in result["risk_flags"]


def _base_decision(**overrides):
    payload = {
        "proposed_direction": "LONG",
        "proposed_size": 1.0,
        "final_size": 1.0,
        "confidence": 0.9,
        "take_profit": 3.0,
        "stop_loss": 1.0,
    }
    payload.update(overrides)
    return payload


def test_decision_fusion_shrinks_size_on_high_volatility():
    fusion = DecisionFusion()
    calm_ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision=_base_decision(),
    )
    volatile_ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 5, "volume_ratio": 1}},
        decision=_base_decision(),
    )

    calm_result = fusion.evaluate(calm_ctx, None)
    volatile_result = fusion.evaluate(volatile_ctx, None)

    assert calm_result.decision.final_size > 0
    assert volatile_result.decision.final_size < calm_result.decision.final_size
    logged = [i for i in volatile_result.cognition.relevant_knowledge if i.get("type") == "inner_critic"]
    assert len(logged) == 1
    assert "high_volatility" in logged[0]["data"]["risk_flags"]


def test_decision_fusion_reduces_confidence_on_memory_direction_conflict(monkeypatch):
    # calibrate_confidence gerçek DB'deki (paylaşılan test ortamı, kırılgan)
    # ampirik eğriye bağlı — burada izole etmek için identity'e sabitleniyor
    # (bu turdaki red-team testi düzeltmesinde kurulan AYNI desen).
    monkeypatch.setattr("services.decision_fusion.calibrate_confidence", lambda c: c)
    fusion = DecisionFusion()

    # confidence=0.4, win=3, loss=1 -> breakeven confidence 0.25 — EV
    # pozitif ama marjinal; %50'e yakın bir indirim EV'yi negatife çeker.
    agreeing_ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision=_base_decision(confidence=0.4),
    )
    agreeing_ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"dominant_direction": "LONG", "confidence": 0.9},
    })

    conflicting_ctx = CognitiveCycleContext(
        market={"features": {"RSI": 50, "ATR": 1, "volume_ratio": 1}},
        decision=_base_decision(confidence=0.4),
    )
    conflicting_ctx.cognition.relevant_knowledge.append({
        "type": "memory_insight",
        "data": {"dominant_direction": "SHORT", "confidence": 0.9},
    })

    agreeing_result = fusion.evaluate(agreeing_ctx, None)
    conflicting_result = fusion.evaluate(conflicting_ctx, None)

    assert agreeing_result.decision.final_size > 0
    # Aynı ham girdilerle, çelişen hafıza EV'yi negatife çekmeli -> ret.
    assert conflicting_result.decision.final_size == 0
    assert conflicting_result.decision.action.value == "WAIT"
