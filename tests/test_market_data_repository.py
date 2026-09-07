"""Market Data Service sprint: contracts/market_data.py::MarketSnapshot was
a well-designed, unused contract — this proves the real DB round trip that
was missing (faz184 migration + MarketDataRepository)."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory


def test_upsert_snapshot_is_idempotent_and_updates_on_conflict():
    symbol = f"MDTEST{uuid4().hex[:6]}"
    ts = datetime.now(UTC).replace(microsecond=0)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        repo.upsert_snapshot(MarketSnapshot(
            time=ts, exchange=DataSource.BINANCE, symbol=symbol, resolution=Resolution.M1,
            open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0, source_version="v1",
        ))
        # Same (exchange, symbol, resolution, time) again, different close
        # (simulates re-fetching a candle before it closes) — must update,
        # not duplicate.
        repo.upsert_snapshot(MarketSnapshot(
            time=ts, exchange=DataSource.BINANCE, symbol=symbol, resolution=Resolution.M1,
            open=100.0, high=102.0, low=99.0, close=101.5, volume=15.0, source_version="v1",
        ))

        rows = repo.get_latest_snapshots(DataSource.BINANCE, symbol, Resolution.M1, limit=10)

    assert len(rows) == 1
    assert rows[0].close == 101.5
    assert rows[0].volume == 15.0


def test_get_latest_snapshots_returns_oldest_to_newest():
    symbol = f"MDTEST{uuid4().hex[:6]}"
    base = datetime.now(UTC).replace(microsecond=0)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(3):
            repo.upsert_snapshot(MarketSnapshot(
                time=base + timedelta(minutes=i), exchange=DataSource.BINANCE, symbol=symbol,
                resolution=Resolution.M1, open=100.0 + i, high=101.0 + i, low=99.0 + i,
                close=100.5 + i, volume=10.0, source_version="v1",
            ))

        rows = repo.get_latest_snapshots(DataSource.BINANCE, symbol, Resolution.M1, limit=10)

    assert [r.close for r in rows] == [100.5, 101.5, 102.5]


def test_trade_persisted_and_retrievable():
    symbol = f"MDTRADE{uuid4().hex[:6]}"

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        repo.save_trade(
            exchange=DataSource.BINANCE, symbol=symbol, price=50000.0, quantity=0.01,
            time=datetime.now(UTC), side="buy",
        )
        trades = repo.get_recent_trades(symbol, limit=10)

    assert len(trades) == 1
    assert trades[0]["price"] == 50000.0
    assert trades[0]["side"] == "buy"


def test_get_recent_order_book_snapshots_returns_newest_first():
    """Faz 436 — kullanıcı önceliği ①: OI+Funding+Price'ı BİRLİKTE
    değerlendirmek için bir zaman serisi gerekiyor — get_latest_order_
    book_snapshot tek satır dönüyordu, yetersizdi."""
    symbol = f"OBTEST{uuid4().hex[:6]}USDT"
    base = datetime.now(UTC).replace(microsecond=0)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(3):
            repo.save_order_book_snapshot(
                exchange=DataSource.BINANCE, symbol=symbol, time=base + timedelta(minutes=i),
                best_bid=100.0 + i, best_ask=100.1 + i, bid_volume=10.0, ask_volume=10.0,
                imbalance=0.0, spread_bps=1.0, aggressive_buy_ratio=0.5,
                funding_rate=0.0001 * i, open_interest=1000.0 + i * 10, open_interest_trend="stable",
            )
        rows = repo.get_recent_order_book_snapshots(DataSource.BINANCE, symbol, limit=10)

    assert len(rows) == 3
    assert [r["best_bid"] for r in rows] == [102.0, 101.0, 100.0]  # en yeni ilk


def test_get_recent_order_book_snapshots_is_empty_for_never_ingested_symbol():
    symbol = f"OBTEST{uuid4().hex[:6]}NEVERUSDT"
    with SessionFactory.get_session() as session:
        rows = MarketDataRepository(session).get_recent_order_book_snapshots(DataSource.BINANCE, symbol, limit=10)
    assert rows == []
