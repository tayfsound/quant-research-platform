"""Faz 191: kritik bulgu — DecisionFusion, ctx.decision.take_profit/stop_loss'a
bakıp Expected Value hesaplıyordu ama hiçbir kod bu ikisini hiçbir zaman set
etmiyordu (hep None -> win=0, loss=0, ev her zaman <=0). Bu, Council ne
önerirse önersin HER işlemi WAIT'e zorluyordu — sistemin bu oturumda inşa
edilen tüm gerçek pozisyon yaşam döngüsü (Faz 187-190) hiçbir zaman gerçek
bir pozisyon açamıyordu. RiskTargetStage bunu gerçek ATR'den (signal_engine.py)
standart bir 1:2 risk/ödül hedefiyle kapatıyor."""
from engines.cognitive_pipeline import RiskTargetStage
from services.decision_fusion import DecisionFusion
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from contracts.belief import Belief


def _ctx(direction="LONG", atr=100.0, confidence=0.6):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.market.features = {"atr": atr}
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = 0.3
    ctx.decision.final_size = 0.3
    ctx.decision.confidence = confidence
    # MetaStage, DecisionFusion çalışmadan ÖNCE action'ı ENTER_LONG/SHORT'a
    # set eder (bkz. engines/cognitive_pipeline.py:MetaStage) — burada onu
    # elle taklit ediyoruz. DecisionFusion sadece REDDEDERKEN action'ı
    # WAIT'e zorluyor, onayladığında dokunmuyor.
    if direction == "LONG":
        ctx.decision.action = ActionType.ENTER_LONG
    elif direction == "SHORT":
        ctx.decision.action = ActionType.ENTER_SHORT
    return ctx


def _belief(direction="LONG", strength=0.6):
    return Belief(direction=direction, strength=strength)


def test_risk_target_stage_sets_take_profit_and_stop_loss_from_real_atr():
    ctx = _ctx(direction="LONG", atr=100.0)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss == 100.0  # 1x ATR
    assert ctx.decision.take_profit == 200.0  # 2x ATR


def test_risk_target_stage_leaves_targets_unset_for_wait():
    ctx = _ctx(direction="WAIT", atr=100.0)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss is None
    assert ctx.decision.take_profit is None


def test_risk_target_stage_leaves_targets_unset_when_no_real_atr():
    """ATR yoksa (yetersiz veri) hedef icat edilmiyor — DecisionFusion
    dürüstçe reddetmeye devam ediyor, sahte bir sayı üretilmiyor."""
    ctx = _ctx(direction="LONG", atr=0.0)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss is None
    assert ctx.decision.take_profit is None


def test_decision_fusion_no_longer_forces_wait_once_real_targets_are_set():
    """Bu, gerçek bulgunun kanıtı: RiskTargetStage olmadan (take_profit/
    stop_loss None) DecisionFusion HER ZAMAN ev<=0 -> WAIT üretiyordu.
    RiskTargetStage'in gerçek ATR'den kurduğu 1:2 hedefle, makul bir
    confidence'ta artık pozitif EV ile onaylanabiliyor."""
    ctx = _ctx(direction="LONG", atr=100.0, confidence=0.6)
    ctx = RiskTargetStage().execute(ctx)

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.6))

    assert ctx.decision.action.value != "WAIT"
    assert ctx.decision.final_size > 0


def test_decision_fusion_still_forces_wait_without_risk_target_stage():
    """Regresyon kilidi: RiskTargetStage atlanırsa (eski, bug'lı davranış)
    DecisionFusion hâlâ her zaman WAIT'e zorlamalı — bu testin kendisi
    orijinal bug'ı belgeliyor."""
    ctx = _ctx(direction="LONG", atr=100.0, confidence=0.9)
    # RiskTargetStage.execute() KASITLI OLARAK çağrılmıyor.

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.9))

    assert ctx.decision.action.value == "WAIT"
    assert ctx.decision.final_size == 0.0
