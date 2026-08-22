"""Faz 210: kullanıcı bulgusu — ilk gerçek kapanan işlemler (PAXGUSDT,
XAUTUSDT) gerçekten take_profit hedefine ulaştı ama net PnL yine de eksiye
düştü, çünkü ATR-tabanlı hedef ($ olarak) bu fiyat seviyesinde round-trip
komisyona kıyasla çok küçüktü. DecisionFusion artık hedefin fiyata oranını
(win/current_price) app_settings'teki min_profit_target_pct'e karşı
kontrol ediyor."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from database.repositories.app_settings_repository import DEFAULTS, AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_fusion import DecisionFusion


def _ctx(current_price: float, take_profit: float, stop_loss: float, confidence: float = 0.6):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "PAXGUSDT"
    ctx.market.raw_snapshot = {"close": current_price}
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.proposed_size = 1.0
    ctx.decision.final_size = 1.0
    ctx.decision.confidence = confidence
    ctx.decision.take_profit_distance = take_profit
    ctx.decision.stop_loss_distance = stop_loss
    ctx.decision.action = ActionType.ENTER_LONG
    return ctx


def _reset_setting():
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "min_profit_target_pct", DEFAULTS["min_profit_target_pct"], updated_by="test",
        )


def test_target_far_below_min_profit_pct_is_rejected_like_paxgusdt():
    """Gerçek olay: entry ~4275, take_profit sadece ~3 (aradaki fark) —
    hedef fiyatın %0.07'si, komisyonu (~%0.1) bile karşılamıyor."""
    try:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("min_profit_target_pct", "0.005", updated_by="test")

        ctx = _ctx(current_price=4275.0, take_profit=3.0, stop_loss=1.5, confidence=0.78)
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.78))

        assert ctx.decision.action.value == "WAIT"
        assert ctx.decision.final_size == 0.0
    finally:
        _reset_setting()


def test_target_above_min_profit_pct_is_approved():
    try:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("min_profit_target_pct", "0.005", updated_by="test")

        # take_profit = %1 of price, comfortably above the %0.5 floor.
        ctx = _ctx(current_price=100.0, take_profit=1.0, stop_loss=0.5, confidence=0.6)
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.6))

        assert ctx.decision.action.value != "WAIT"
        assert ctx.decision.final_size > 0
    finally:
        _reset_setting()


def test_zero_min_profit_pct_disables_the_gate():
    try:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("min_profit_target_pct", "0", updated_by="test")

        ctx = _ctx(current_price=4275.0, take_profit=3.0, stop_loss=1.5, confidence=0.78)
        ctx = DecisionFusion().evaluate(ctx, Belief(direction="LONG", strength=0.78))

        assert ctx.decision.action.value != "WAIT"
    finally:
        _reset_setting()
