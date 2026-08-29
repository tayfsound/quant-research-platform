"""Faz 372 — DecisionFusion içindeki SHORT Exploration entegrasyonu.

bkz. services/short_exploration.py (eligibility mantığı, ayrıca test
edildi — tests/test_short_exploration.py), services/decision_fusion.py
(çağrı noktası). Burada SADECE entegrasyonun (ev<=0 + SHORT + eligible ->
tiny size + experiment_bucket; ev<=0 + LONG -> davranış DEĞİŞMEDİ)
doğru kablolandığını doğruluyoruz — is_eligible'ın kendi mantığı
monkeypatch'lendi."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.decision_fusion import DecisionFusion
from services.short_exploration import EXPERIMENT_BUCKET


def _ctx(direction: str, take_profit: float, stop_loss: float, confidence: float, proposed_size: float = 10.0):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "SOLUSDT"
    ctx.market.raw_snapshot = {"close": 100.0}
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = proposed_size
    ctx.decision.final_size = proposed_size
    ctx.decision.confidence = confidence
    ctx.decision.take_profit_distance = take_profit
    ctx.decision.stop_loss_distance = stop_loss
    return ctx


def _relevant_knowledge_types(ctx):
    return [item.get("type") for item in ctx.cognition.relevant_knowledge]


def test_negative_ev_short_opens_tiny_exploration_position_when_eligible(monkeypatch):
    monkeypatch.setattr("services.short_exploration.is_eligible", lambda symbol, confidence: (True, None))

    # win/loss öyle seçildi ki EV kesin negatif olsun (loss >> win, düşük confidence).
    ctx = _ctx("SHORT", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="SHORT", strength=0.3))

    assert ctx.decision.action == ActionType.ENTER_SHORT
    # Faz 372'nin SIZE_MULTIPLIER'ı (0.1) taban alınıyor, ama R:R çok düşükse
    # (bu testte bilerek öyle kurgulandı) DecisionFusion'ın kendi "risk/ödül
    # çok düşük, yarıya indir" kuralı de AYNEN uygulanmaya devam ediyor —
    # exploration bu ek güvenliği atlamıyor, sadece EV kapısını.
    assert 0.0 < ctx.decision.final_size <= 10.0 * 0.1
    assert "experiment_bucket" in _relevant_knowledge_types(ctx)
    bucket_item = next(i for i in ctx.cognition.relevant_knowledge if i["type"] == "experiment_bucket")
    assert bucket_item["data"]["bucket"] == EXPERIMENT_BUCKET


def test_negative_ev_short_stays_waiting_when_not_eligible(monkeypatch):
    monkeypatch.setattr(
        "services.short_exploration.is_eligible",
        lambda symbol, confidence: (False, "weekly_budget_exhausted"),
    )

    ctx = _ctx("SHORT", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="SHORT", strength=0.3))

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert "experiment_bucket" not in _relevant_knowledge_types(ctx)
    fusion_item = next(i for i in ctx.cognition.relevant_knowledge if i["type"] == "decision_fusion")
    assert fusion_item["data"]["short_exploration_rejected_reason"] == "weekly_budget_exhausted"


def test_negative_ev_long_is_completely_unaffected_by_short_exploration(monkeypatch):
    """Kritik regresyon: exploration mekanizması SADECE SHORT'u etkilemeli
    — LONG'un negatif-EV davranışı birebir eskisiyle aynı kalmalı."""
    monkeypatch.setattr(
        "services.short_exploration.is_eligible",
        lambda symbol, confidence: (True, None),  # eligible=True olsa bile LONG'u etkilememeli
    )

    ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0)
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3))

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert "experiment_bucket" not in _relevant_knowledge_types(ctx)


def test_short_with_no_real_tp_sl_distances_is_not_explored(monkeypatch):
    """MetaStage zaten WAIT dediyse (RiskTargetStage hiç çalışmamış olur)
    win=loss=0 kalır — exploration için gerçek bir risk/ödül yok, denemeye
    hiç girilmemeli (is_eligible çağrılmamalı bile)."""
    calls = []
    monkeypatch.setattr(
        "services.short_exploration.is_eligible",
        lambda symbol, confidence: calls.append(1) or (True, None),
    )

    ctx = _ctx("SHORT", take_profit=0.0, stop_loss=0.0, confidence=0.3, proposed_size=10.0)
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="SHORT", strength=0.3))

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert calls == []
