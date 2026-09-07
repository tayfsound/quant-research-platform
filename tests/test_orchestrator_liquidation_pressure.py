"""services/orchestrator.py::build_cognitive_context — Faz 439
(2026-09-08). tests/test_orchestrator_order_flow_relationship.py İLE
AYNI desen: ctx.market.features artık liquidation_pressure_* alanlarını
taşıyor, SADECE gözlem, hiçbir agent'ın skoruna girmiyor.

Bu ortamda `liquidation_events` GERÇEKTEN hiç dolmuyor (coğrafi WS
kısıtı) — bu test SENTETİK satırlar yazarak wiring'i doğruluyor, üretim
sunucusunda gerçek veriyle AYRICA doğrulanmalı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import build_cognitive_context


def _flat_bars(n: int = 30) -> list[OHLCV]:
    base = datetime.now(UTC)
    return [
        OHLCV(timestamp=base + timedelta(hours=i), open=100.0, high=100.1, low=99.9, close=100.0, volume=10.0)
        for i in range(n)
    ]


def _insert_liquidation(session, *, symbol: str, side: str, notional_usd: float, time) -> None:
    session.execute(
        text("""
            INSERT INTO liquidation_events (symbol, time, liquidated_side, price, quantity, notional_usd)
            VALUES (:symbol, :time, :side, 100.0, :quantity, :notional_usd)
        """),
        {"symbol": symbol, "time": time, "side": side, "quantity": notional_usd / 100.0, "notional_usd": notional_usd},
    )


def test_liquidation_pressure_keys_absent_for_a_symbol_with_no_events():
    symbol = f"LPTEST{uuid4().hex[:6]}NEVERUSDT"
    ctx = build_cognitive_context(symbol, "1h", _flat_bars())
    assert ctx.market.features["liquidation_pressure_category"] == "no_data"


def test_liquidation_pressure_is_populated_from_real_liquidation_events():
    symbol = f"LPTEST{uuid4().hex[:6]}USDT"
    now = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        # fetch_liquidation_pressure() sorgudan ÖNCE symbol.upper() yapıyor
        # (uuid4().hex küçük harfli hex üretir) -- kaydı da AYNI biçimde
        # (upper) yazmak gerekiyor, aksi halde eşleşme sessizce boş döner.
        _insert_liquidation(session, symbol=symbol.upper(), side="LONG", notional_usd=40_000.0, time=now - timedelta(minutes=10))
        _insert_liquidation(session, symbol=symbol.upper(), side="SHORT", notional_usd=5_000.0, time=now - timedelta(minutes=5))
        session.commit()

    ctx = build_cognitive_context(symbol, "1h", _flat_bars())

    assert ctx.market.features["liquidation_pressure_category"] == "long_liquidation_dominant"
    assert ctx.market.features["liquidation_pressure_long_usd"] == 40_000.0
    assert ctx.market.features["liquidation_pressure_short_usd"] == 5_000.0
