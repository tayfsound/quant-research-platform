"""services/orchestrator.py::build_cognitive_context — Faz 436 (kullanıcı
önceliği ①, 2026-09-07). ctx.market.features artık her cycle'da
order_flow_relationship_* alanlarını taşıyor — data_quality_score/
high_impact_event_imminent İLE AYNI desen, SADECE gözlem, hiçbir agent'ın
skoruna girmiyor. tests/test_orchestrator_confluence_zones.py'deki AYNI
build_cognitive_context çağrı deseni."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.market_data import DataSource
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import build_cognitive_context


def _flat_bars(n: int = 30) -> list[OHLCV]:
    base = datetime.now(UTC)
    return [
        OHLCV(timestamp=base + timedelta(hours=i), open=100.0, high=100.1, low=99.9, close=100.0, volume=10.0)
        for i in range(n)
    ]


def test_order_flow_relationship_keys_absent_for_a_never_ingested_symbol():
    """Fail-closed: order_book_snapshots hiç yoksa cycle patlamamalı,
    sadece yeni alanlar eklenmemeli."""
    symbol = f"OFRTEST{uuid4().hex[:6]}NEVERUSDT"
    ctx = build_cognitive_context(symbol, "1h", _flat_bars())
    assert "order_flow_relationship_category" not in ctx.market.features


def test_order_flow_relationship_is_populated_from_real_order_book_snapshots():
    symbol = f"OFRTEST{uuid4().hex[:6]}USDT"
    base = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        repo.save_order_book_snapshot(
            exchange=DataSource.BINANCE, symbol=symbol, time=base - timedelta(minutes=30),
            best_bid=100.0, best_ask=100.1, bid_volume=10.0, ask_volume=10.0,
            imbalance=0.0, spread_bps=1.0, aggressive_buy_ratio=0.5,
            funding_rate=0.0001, open_interest=1000.0, open_interest_trend="stable",
        )
        repo.save_order_book_snapshot(
            exchange=DataSource.BINANCE, symbol=symbol, time=base,
            best_bid=105.0, best_ask=105.1, bid_volume=10.0, ask_volume=10.0,
            imbalance=0.0, spread_bps=1.0, aggressive_buy_ratio=0.5,
            funding_rate=0.0003, open_interest=1100.0, open_interest_trend="rising",
        )

    ctx = build_cognitive_context(symbol, "1h", _flat_bars())

    assert ctx.market.features["order_flow_relationship_category"] == "bullish_new_longs"
    assert ctx.market.features["order_flow_relationship_price_change_pct"] > 0
    assert ctx.market.features["order_flow_relationship_oi_change_pct"] > 0
    assert ctx.market.features["order_flow_relationship_funding_rate"] == 0.0003
