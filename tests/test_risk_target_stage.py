"""Faz 191: kritik bulgu — DecisionFusion, ctx.decision.take_profit/stop_loss'a
bakıp Expected Value hesaplıyordu ama hiçbir kod bu ikisini hiçbir zaman set
etmiyordu (hep None -> win=0, loss=0, ev her zaman <=0). Bu, Council ne
önerirse önersin HER işlemi WAIT'e zorluyordu — sistemin bu oturumda inşa
edilen tüm gerçek pozisyon yaşam döngüsü (Faz 187-190) hiçbir zaman gerçek
bir pozisyon açamıyordu. RiskTargetStage bunu gerçek ATR'den (signal_engine.py)
standart bir risk/ödül hedefiyle kapatıyor.

Faz 251: kritik bulgu — sinyal zaman diliminin (candle_timeframe, genelde
1m) ATR'si kripto gibi yüksek volatiliteli bir piyasada bile gürültü
seviyesinde kalıyordu (gerçek ölçüm: BTCUSDT 1m ATR fiyatın ~%0.05'i) —
stop, bir mumun sıradan dalgalanmasından bile küçük kalıp anında
tetikleniyordu (kullanıcı bulgusu: $1900'lük pozisyonlarda $0.07 stop
gibi anlamsız değerler). Artık günlük ATR YÜZDESİ (sinyal zaman
diliminden bağımsız) + güncel fiyattan türetiliyor, 2.5x/5x çarpanla."""
from engines.cognitive_pipeline import RiskTargetStage
from services.decision_fusion import DecisionFusion
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from contracts.belief import Belief


def _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0, confidence=0.6):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.market.features = {"daily_atr_pct": daily_atr_pct}
    ctx.market.raw_snapshot = {"close": current_price}
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


def test_risk_target_stage_sets_take_profit_and_stop_loss_from_daily_atr_pct():
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx = RiskTargetStage().execute(ctx)

    assert abs(ctx.decision.stop_loss - 5.0) < 1e-9  # 100 * 2.5 * 0.02
    # Faz 268-sonrası: gerçek OOS doğrulaması 1:4'ün (2.5x/10.0x) tersini
    # işaret etti — hedef, stop'tan KÜÇÜK olmalı (bkz. app_settings_
    # repository.py::DEFAULTS["target_atr_mult"] üstündeki not).
    # Varsayılan artık 1.4x — 100 * 1.4 * 0.02 = 2.8.
    assert abs(ctx.decision.take_profit - 2.8) < 1e-9


def test_risk_target_stage_leaves_targets_unset_for_wait():
    ctx = _ctx(direction="WAIT", daily_atr_pct=0.02)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss is None
    assert ctx.decision.take_profit is None


def test_risk_target_stage_leaves_targets_unset_when_no_daily_atr():
    """Günlük ATR yoksa (yetersiz veri) hedef icat edilmiyor —
    DecisionFusion dürüstçe reddetmeye devam ediyor, sahte bir sayı
    üretilmiyor."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.0)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss is None
    assert ctx.decision.take_profit is None


def test_decision_fusion_no_longer_forces_wait_once_real_targets_are_set():
    """Bu, gerçek bulgunun kanıtı: RiskTargetStage olmadan (take_profit/
    stop_loss None) DecisionFusion HER ZAMAN ev<=0 -> WAIT üretiyordu.
    RiskTargetStage'in günlük ATR'den kurduğu hedefle, makul bir
    confidence'ta artık pozitif EV ile onaylanabiliyor.

    Faz 268-sonrası: yeni varsayılan oran (1:0.56) breakeven için daha
    yüksek bir kazanma olasılığı gerektiriyor (~%64, eski 1:4 oranın
    %20'sinin tersine) — bu test artık daha yüksek bir confidence/
    strength kullanıyor, hâlâ pozitif EV'nin gerçekten üretildiğini
    kanıtlamak için."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0, confidence=0.85)
    ctx = RiskTargetStage().execute(ctx)

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.85))

    assert ctx.decision.action.value != "WAIT"
    assert ctx.decision.final_size > 0


def test_multipliers_are_read_from_app_settings_not_hardcoded():
    """Faz 268-sonrası — kritik bulgu: STOP_ATR_MULT/TARGET_ATR_MULT eskiden
    sınıf sabitiydi, DSR henüz kanıtlanmamışken bu oranı hızla ayarlamak
    redeploy gerektiriyordu. Artık AppSettings'ten okunuyor."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("target_atr_mult", "3.0", updated_by="test")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.take_profit - 6.0) < 1e-9  # 100 * 3.0 * 0.02
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("target_atr_mult", "1.4", updated_by="test")


def test_decision_fusion_still_forces_wait_without_risk_target_stage():
    """Regresyon kilidi: RiskTargetStage atlanırsa (eski, bug'lı davranış)
    DecisionFusion hâlâ her zaman WAIT'e zorlamalı — bu testin kendisi
    orijinal bug'ı belgeliyor."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, confidence=0.9)
    # RiskTargetStage.execute() KASITLI OLARAK çağrılmıyor.

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.9))

    assert ctx.decision.action.value == "WAIT"
    assert ctx.decision.final_size == 0.0
