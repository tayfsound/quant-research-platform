"""Faz 315 — Execution Layer, Faz 1: PositionCloser'ın testnet
bağlantısı — breakeven ratchet borsadaki GERÇEK stop emrini günceller,
kapanış kontrolü kendi iç fiyat-karşılaştırmasını (BOME/MUBARAK'ta
gecikmeye yol açan tam o mekanizma) atlayıp borsanın gerçek durumunu
sorar. Sahte ExecutionService ile — gerçek ağ/anahtar gerektirmez."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from contracts.exchange import OrderSide, OrderStatus
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.execution_service import StopUpdateResult
from services.position_closer import PositionCloser


class _FixedPriceProvider:
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def _persist_testnet_position(symbol, stop_loss_price=90.0, take_profit_price=140.0,
                               exchange_stop_order_id="STOP1", exchange_tp_order_id="TP1"):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        stop_loss_price=stop_loss_price, take_profit_price=take_profit_price,
        execution_mode="testnet",
        exchange_order_id="ENTRY1", exchange_client_order_id="qrpe1",
        exchange_stop_order_id=exchange_stop_order_id, exchange_tp_order_id=exchange_tp_order_id,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def test_apply_breakeven_stop_testnet_updates_using_the_stop_orders_exchange_id_not_the_entry_orders():
    """Faz 315 regresyon kilidi — bulunan gerçek bug: _apply_breakeven_
    stop_testnet başta yanlışlıkla exchange_client_order_id'yi (SADECE
    giriş emrinde var) update_stop_price'a old_stop_order_id olarak
    veriyordu. Koruma emirlerinin (stop/TP) client_order_id'si DB'de
    hiç saklanmıyor — SADECE exchange_stop_order_id/exchange_tp_order_id
    var. Bu test, doğru alanın kullanıldığını kanıtlıyor."""

    class _FakeExecutionService:
        def __init__(self):
            self.update_stop_price_calls = []

        def is_configured(self) -> bool:
            return True

        def update_stop_price(self, **kwargs):
            self.update_stop_price_calls.append(kwargs)
            return StopUpdateResult(new_stop_order_id="STOP2", achieved_stop_price=kwargs["new_stop_price"])

    fake_service = _FakeExecutionService()
    closer = PositionCloser(_FixedPriceProvider(100.0), execution_service=fake_service)
    pos = {
        "id": uuid4(), "symbol": "BTCUSDT", "direction": "LONG", "quantity": 1.0,
        "stop_loss_price": 90.0, "execution_mode": "testnet", "exchange_stop_order_id": "STOP1",
        "exchange_client_order_id": "qrpe1",
    }

    with SessionFactory.get_session() as session:
        result = closer._apply_breakeven_stop_testnet(pos, 95.0, DecisionPersistor(session))

    assert result == 95.0
    assert len(fake_service.update_stop_price_calls) == 1
    call = fake_service.update_stop_price_calls[0]
    assert call["old_stop_order_id"] == "STOP1"
    assert "old_stop_client_order_id" not in call


def test_check_testnet_exit_returns_none_when_exchange_still_shows_open_position():
    class _FakeExecutionService:
        def is_configured(self) -> bool:
            return True

        def get_open_position(self, symbol):
            return {"symbol": symbol, "positionAmt": "1.0"}

        def get_order_status(self, symbol, order_id):
            raise AssertionError("pozisyon hâlâ açıkken emir durumu sorgulanmamalı")

    closer = PositionCloser(_FixedPriceProvider(100.0), execution_service=_FakeExecutionService())
    reason, price = closer._check_testnet_exit({"symbol": "BTCUSDT", "exchange_stop_order_id": "S1", "exchange_tp_order_id": "T1"})
    assert (reason, price) == (None, None)


def test_check_testnet_exit_returns_stop_loss_when_stop_order_filled():
    class _FakeExecutionService:
        def is_configured(self) -> bool:
            return True

        def get_open_position(self, symbol):
            return None

        def get_order_status(self, symbol, order_id):
            if order_id == "S1":
                return OrderStatus(exchange_order_id="S1", client_order_id="qrps1", status="FILLED",
                                    executed_qty=1.0, avg_price=89.5, side=OrderSide.SELL)
            return None

    closer = PositionCloser(_FixedPriceProvider(100.0), execution_service=_FakeExecutionService())
    reason, price = closer._check_testnet_exit(
        {"symbol": "BTCUSDT", "exchange_stop_order_id": "S1", "exchange_tp_order_id": "T1", "stop_loss_price": 90.0}
    )
    assert reason == "stop_loss"
    assert price == 89.5


def test_check_testnet_exit_returns_take_profit_when_tp_order_filled():
    class _FakeExecutionService:
        def is_configured(self) -> bool:
            return True

        def get_open_position(self, symbol):
            return None

        def get_order_status(self, symbol, order_id):
            if order_id == "T1":
                return OrderStatus(exchange_order_id="T1", client_order_id="qrpt1", status="FILLED",
                                    executed_qty=1.0, avg_price=140.5, side=OrderSide.SELL)
            return None

    closer = PositionCloser(_FixedPriceProvider(100.0), execution_service=_FakeExecutionService())
    reason, price = closer._check_testnet_exit(
        {"symbol": "BTCUSDT", "exchange_stop_order_id": "S1", "exchange_tp_order_id": "T1", "take_profit_price": 140.0}
    )
    assert reason == "take_profit"
    assert price == 140.5


def test_close_due_positions_uses_exchange_state_for_testnet_positions_not_internal_price_comparison():
    """close_due_positions'ın testnet dalı, kendi iç fiyat-karşılaştırma
    mantığını (BOME/MUBARAK'ta gecikmeye yol açan mekanizma) HİÇ
    kullanmamalı — borsanın GERÇEK durumu belirleyici olmalı. Güncel
    fiyat (200) take_profit'in (110) çok üzerinde — SİMÜLE modda bu anlık
    '_exit_reason' ile take_profit olarak kapanırdı. testnet modda ise
    borsa hâlâ 'açık' dediği sürece (get_open_position None DEĞİL)
    pozisyon bu turda KAPANMAMALI, sadece breakeven ratchet'i tetiklenir."""
    symbol = f"POSEXECTN{uuid4().hex[:8]}"
    event = _persist_testnet_position(symbol, stop_loss_price=90.0, take_profit_price=110.0)

    class _FakeExecutionService:
        def is_configured(self) -> bool:
            return True

        def get_open_position(self, symbol):
            return {"symbol": symbol, "positionAmt": "1.0"}

        def get_order_status(self, symbol, order_id):
            return None

        def update_stop_price(self, **kwargs):
            # current_price=200 entry'nin çok üzerinde — breakeven/trailing
            # ratchet gerçekten tetiklenir, gerçek borsa emrini günceller.
            return StopUpdateResult(new_stop_order_id="STOP2", achieved_stop_price=kwargs["new_stop_price"])

    try:
        closer = PositionCloser(_FixedPriceProvider(200.0), execution_service=_FakeExecutionService())
        with SessionFactory.get_session() as session:
            closed = closer.close_due_positions(DecisionPersistor(session))

        assert str(event.id) not in {c["decision_id"] for c in closed}

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(event.id))
        assert row["status"] == "open"
    finally:
        # Faz 363 — bu test kasıtlı olarak pozisyonu 'open' bırakıyor (asıl
        # amacı bu), bu yüzden temizlenmezse paylaşılan test DB'sinde kalıcı
        # bir testnet/open yetim kayıt olarak kalıyor. close_due_positions()
        # gibi TÜM açık pozisyonları tarayan başka testler buna rastlayınca
        # gerçek Binance testnet API'sine bağlanmaya çalışıp "Invalid symbol"
        # ile patlıyordu (bkz. tests/test_decision_recorder_execution_mode.py
        # aynı desendeki düzeltme).
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()


def test_close_due_positions_closes_testnet_position_using_real_exchange_fill_price():
    symbol = f"POSEXCLOSE{uuid4().hex[:8]}"
    event = _persist_testnet_position(symbol, stop_loss_price=90.0, take_profit_price=110.0)

    class _FakeExecutionService:
        def is_configured(self) -> bool:
            return True

        def get_open_position(self, symbol):
            return None  # borsada artık pozisyon yok -> gerçekten kapanmış

        def get_order_status(self, symbol, order_id):
            if order_id == "STOP1":
                return OrderStatus(exchange_order_id="STOP1", client_order_id="qrps1", status="FILLED",
                                    executed_qty=1.0, avg_price=88.7, side=OrderSide.SELL)
            return None

    closer = PositionCloser(_FixedPriceProvider(88.0), execution_service=_FakeExecutionService())
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    closed_ids = {c["decision_id"]: c for c in closed}
    assert str(event.id) in closed_ids
    assert closed_ids[str(event.id)]["exit_reason"] == "stop_loss"

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))
    assert row["status"] == "closed"
    # Uydurma bir dolum fiyatı DEĞİL — borsanın GERÇEK avg_price'ı.
    assert row["exit_price"] == 88.7
