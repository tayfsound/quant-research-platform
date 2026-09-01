"""Faz 399 — DecisionFusion'ın negatif-EV reddine test-modu istisnası.

Gerçek bulgu: services/decision_fusion.py'nin negatif-EV reddi hiç
trading_mode kontrol etmiyordu, pipeline'da MetaStage'in Faz 388
test-modu WAIT->REDUCE dönüşümünden SONRA çalıştığı için o korumayı
sessizce geri alıyordu — son 2 günde test modunda 9339 yönlü (LONG/
SHORT) kararın 9300'ü hiçbir gate_block izi bırakmadan tam burada
WAIT'e düşmüştü. tests/test_decision_fusion_short_exploration.py'deki
AYNI desen: SADECE kablolamayı doğruluyoruz."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.decision_fusion import DecisionFusion


def _ctx(direction: str, take_profit: float, stop_loss: float, confidence: float,
         proposed_size: float = 10.0, trading_mode: str = "live"):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "SOLUSDT"
    ctx.market.raw_snapshot = {"close": 100.0}
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = proposed_size
    ctx.decision.final_size = proposed_size
    ctx.decision.confidence = confidence
    ctx.decision.take_profit_distance = take_profit
    ctx.decision.stop_loss_distance = stop_loss
    ctx.risk.trading_mode = trading_mode
    return ctx


def _relevant_knowledge_types(ctx):
    return [item.get("type") for item in ctx.cognition.relevant_knowledge]


def test_negative_ev_long_reduces_instead_of_waiting_in_test_mode():
    # win/loss = 0.6 (>= 0.5) kasıtlı seçildi -- DecisionFusion'ın ayrı
    # "risk/ödül çok düşük, yarıya indir" kuralının bu testin (sadece
    # test-modu carve-out'unu doğrulayan) formülünü karıştırmaması için.
    ctx = _ctx("LONG", take_profit=6.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0, trading_mode="test")
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3))

    assert ctx.decision.action == ActionType.REDUCE
    assert ctx.decision.final_size > 0.0
    # REDUCE'un kendi formülü (final_size = proposed_size * confidence) --
    # Faz 388'in MetaStage'teki AYNI ilkesiyle tutarlı.
    assert round(ctx.decision.final_size, 4) == round(10.0 * ctx.decision.confidence, 4)
    fusion_item = next(i for i in ctx.cognition.relevant_knowledge if i["type"] == "decision_fusion")
    assert "Test modu" in fusion_item["data"]["adjustment"]


def test_negative_ev_short_reduces_instead_of_waiting_in_test_mode_too():
    """SHORT exploration'ın kendi (ayrı, çok daha dar) uygunluk kapısı
    devre dışıyken (varsayılan monkeypatch yok -> gerçek is_eligible
    büyük ihtimalle reddeder) test-modu istisnası hâlâ devreye girmeli --
    LONG/SHORT ayrımı yapmıyor, force-open/short-exploration'ın AKSİNE."""
    ctx = _ctx("SHORT", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0, trading_mode="test")
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="SHORT", strength=0.3))

    assert ctx.decision.action in (ActionType.REDUCE, ActionType.ENTER_SHORT)
    assert ctx.decision.final_size > 0.0


def test_negative_ev_long_still_waits_in_live_mode():
    """Kritik regresyon: canlı modda hiçbir şey değişmedi -- gerçek
    sermaye riskinde negatif EV hâlâ tam olarak engelliyor."""
    ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0, trading_mode="live")
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3))

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert "decision_fusion" in _relevant_knowledge_types(ctx)
    fusion_item = next(i for i in ctx.cognition.relevant_knowledge if i["type"] == "decision_fusion")
    assert fusion_item["data"]["rejection"] == "Negatif beklenen değer (EV)"


def test_test_mode_carveout_does_not_fire_without_a_real_directional_signal():
    """MetaStage zaten WAIT dediyse (win=loss=0, RiskTargetStage hiç
    çalışmamış) test modunda bile açılacak gerçek bir risk/ödül yok --
    istisna devreye girmemeli."""
    ctx = _ctx("LONG", take_profit=0.0, stop_loss=0.0, confidence=0.3, proposed_size=10.0, trading_mode="test")
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3))

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0


def test_test_mode_carveout_yields_to_agent_combination_force_open(monkeypatch):
    """Force-open zaten uygunsa (gerçek sermaye riskinde bile geçerli,
    daha güçlü bir kanıt) test-modu istisnası onun yerine geçmemeli --
    force-open'ın kendi ENTER_LONG/SHORT + deneysel bucket'ı korunmalı."""
    from services.agent_combination_reliability_force_open import EXPERIMENT_BUCKET

    monkeypatch.setattr(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        lambda self, key: "true" if key in (
            "agent_combination_force_open_enabled",
        ) else None,
    )
    monkeypatch.setattr(
        "database.repositories.agent_combination_reliability_report_repository."
        "AgentCombinationReliabilityReportRepository.get_latest",
        lambda self: {"result": {"pairs": [{
            "domains": ["technical"], "combination_size": 1, "sample_size": 40,
            "win_rate": 0.9, "win_rate_delta_vs_baseline": 0.2, "fdr_significant": True,
            "max_shared_trade_overlap_pct": 0.1, "max_shared_trade_overlap_with": None,
            "distinct_days": 10, "oos_survival": True, "effective_sample_size": 36,
            "gate_eligible": True,
        }]}},
    )
    monkeypatch.setattr(
        "services.agent_combination_reliability_force_open.is_eligible", lambda: (True, None),
    )

    from contracts.agent import AgentDomain, AgentOpinion

    ctx = _ctx("LONG", take_profit=1.0, stop_loss=10.0, confidence=0.3, proposed_size=10.0, trading_mode="test")
    opinions = [AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.5)]
    ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.3), opinions=opinions)

    assert ctx.decision.action == ActionType.ENTER_LONG
    bucket_item = next(i for i in ctx.cognition.relevant_knowledge if i["type"] == "experiment_bucket")
    assert bucket_item["data"]["bucket"] == EXPERIMENT_BUCKET
