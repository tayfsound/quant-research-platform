"""Faz 268-sonrası: PositionCloser gerçekten funding rate maliyetini
düşüyor mu (leverage>1) ve spot (leverage=1.0) için hiç uygulamıyor mu."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from contracts.market_data import DataSource
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from services.position_closer import PositionCloser


class _FixedPriceProvider:
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def _open_leveraged_position(symbol: str, leverage: float, quantity: float = 10.0, entry_price: float = 100.0):
    opened_at = datetime.now(UTC) - timedelta(hours=9)  # 1 gerçek settlement geçmiş olsun
    event = DecisionEvent(
        id=uuid4(), timestamp=opened_at, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=quantity, confidence=0.7,
        status="open", entry_price=entry_price, quantity=quantity, opened_at=opened_at,
        # take_profit_price == entry_price/fiyat: LONG için current_price >=
        # take_profit_price'ı hemen tetikler (gross_pnl=0'a temiz bir şekilde
        # sabitler, testte SADECE funding_cost'u izole etmek için).
        stop_loss_price=50.0, take_profit_price=entry_price, leverage=leverage,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
        MarketDataRepository(session).save_order_book_snapshot(
            exchange=DataSource.BINANCE, symbol=symbol, time=opened_at + timedelta(hours=1),
            best_bid=entry_price, best_ask=entry_price, bid_volume=1.0, ask_volume=1.0,
            imbalance=0.0, spread_bps=1.0, funding_rate=0.001,
        )
    return event


def test_leveraged_position_close_deducts_real_funding_cost():
    symbol = f"FCPOS{uuid4().hex[:8]}"
    event = _open_leveraged_position(symbol, leverage=2.0, quantity=10.0, entry_price=100.0)

    closer = PositionCloser(_FixedPriceProvider(100.0))  # fiyat sabit -> gross_pnl=0, sadece fee+funding görünür
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))

    assert row["status"] == "closed"
    outcome = row["outcome"]
    assert outcome["funding_cost"] > 0  # LONG, pozitif funding -> gerçek bir maliyet
    # notional=1000 (leverage ölçeklenmiş quantity*entry_price), 1 settlement, rate=0.001
    assert abs(outcome["funding_cost"] - 1.0) < 1e-6


def test_spot_position_leverage_one_never_charged_funding():
    symbol = f"FCPOS{uuid4().hex[:8]}"
    event = _open_leveraged_position(symbol, leverage=1.0, quantity=10.0, entry_price=100.0)

    closer = PositionCloser(_FixedPriceProvider(100.0))
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))

    assert row["outcome"]["funding_cost"] == 0.0
