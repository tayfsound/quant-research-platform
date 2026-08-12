"""Faz 268-sonrası: perpetual pozisyon tutma maliyeti (funding rate).
simulator/funding_cost.py'nin matematiği + gerçek DB'den funding_rate
okuması."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.market_data import DataSource
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from simulator.funding_cost import compute_funding_cost


def _save_snapshot(symbol: str, time, funding_rate: float | None) -> None:
    with SessionFactory.get_session() as session:
        MarketDataRepository(session).save_order_book_snapshot(
            exchange=DataSource.BINANCE, symbol=symbol, time=time,
            best_bid=100.0, best_ask=100.1, bid_volume=1.0, ask_volume=1.0,
            imbalance=0.0, spread_bps=1.0, funding_rate=funding_rate,
        )


def test_zero_cost_when_position_held_less_than_one_settlement():
    now = datetime.now(UTC)
    cost = compute_funding_cost(
        symbol="FCTEST", direction="LONG", notional=1000.0,
        opened_at=now, closed_at=now + timedelta(hours=3),
    )
    assert cost == 0.0


def test_zero_cost_when_no_real_funding_rate_history_exists():
    symbol = f"FCTEST{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    cost = compute_funding_cost(
        symbol=symbol, direction="LONG", notional=1000.0,
        opened_at=now, closed_at=now + timedelta(hours=9),
    )
    assert cost == 0.0


def test_long_pays_positive_funding_short_receives_it():
    """Gerçek DB'ye karşı: pozitif funding rate'te LONG öder (maliyet
    pozitif, pnl'den düşer), SHORT alır (maliyet negatif, pnl'e eklenir)."""
    symbol = f"FCTEST{uuid4().hex[:8]}"
    opened_at = datetime.now(UTC)
    closed_at = opened_at + timedelta(hours=9)  # 1 settlement (8s) geçmiş
    _save_snapshot(symbol, opened_at + timedelta(hours=1), 0.001)
    _save_snapshot(symbol, opened_at + timedelta(hours=5), 0.001)

    long_cost = compute_funding_cost(
        symbol=symbol, direction="LONG", notional=10_000.0,
        opened_at=opened_at, closed_at=closed_at,
    )
    short_cost = compute_funding_cost(
        symbol=symbol, direction="SHORT", notional=10_000.0,
        opened_at=opened_at, closed_at=closed_at,
    )

    # notional * avg_funding_rate(0.001) * 1 settlement
    assert abs(long_cost - 10.0) < 1e-6
    assert abs(short_cost - (-10.0)) < 1e-6


def test_cost_scales_with_number_of_real_settlements_elapsed():
    symbol = f"FCTEST{uuid4().hex[:8]}"
    opened_at = datetime.now(UTC)
    closed_at = opened_at + timedelta(hours=25)  # 3 settlement (8s*3=24s) geçmiş
    _save_snapshot(symbol, opened_at + timedelta(hours=1), 0.0005)

    cost = compute_funding_cost(
        symbol=symbol, direction="LONG", notional=10_000.0,
        opened_at=opened_at, closed_at=closed_at,
    )
    # notional * 0.0005 * 3 settlement
    assert abs(cost - 15.0) < 1e-6


def test_averages_multiple_real_funding_rate_readings_within_the_window():
    symbol = f"FCTEST{uuid4().hex[:8]}"
    opened_at = datetime.now(UTC)
    closed_at = opened_at + timedelta(hours=9)
    _save_snapshot(symbol, opened_at + timedelta(hours=1), 0.001)
    _save_snapshot(symbol, opened_at + timedelta(hours=2), 0.003)  # ortalama 0.002

    cost = compute_funding_cost(
        symbol=symbol, direction="LONG", notional=10_000.0,
        opened_at=opened_at, closed_at=closed_at,
    )
    assert abs(cost - 20.0) < 1e-6


def test_ignores_snapshots_outside_the_hold_window():
    symbol = f"FCTEST{uuid4().hex[:8]}"
    opened_at = datetime.now(UTC)
    closed_at = opened_at + timedelta(hours=9)
    _save_snapshot(symbol, opened_at - timedelta(hours=5), 0.05)  # pencereden ÖNCE, sayılmamalı
    _save_snapshot(symbol, opened_at + timedelta(hours=1), 0.001)

    cost = compute_funding_cost(
        symbol=symbol, direction="LONG", notional=10_000.0,
        opened_at=opened_at, closed_at=closed_at,
    )
    assert abs(cost - 10.0) < 1e-6
