"""GET /market-data/ohlcv, /market-data/order-book, /agents/ — dashboard'un
Market Overview + Agents sayfaları için eklenen gerçek okuma endpoint'leri."""
from datetime import datetime, UTC
from uuid import uuid4

from contracts.auth import Role
from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_ohlcv_endpoint_returns_real_persisted_bars():
    symbol = f"MDAPI{uuid4().hex[:6]}"
    with SessionFactory.get_session() as session:
        MarketDataRepository(session).upsert_snapshot(MarketSnapshot(
            time=datetime.now(UTC), exchange=DataSource.BINANCE, symbol=symbol,
            resolution=Resolution.M1, open=10, high=11, low=9, close=10.5, volume=100,
            source_version="v1",
        ))

    resp = _client().get(
        f"/api/v1/market-data/ohlcv?symbol={symbol}&resolution=1m",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert resp.status_code == 200
    bars = resp.json()["bars"]
    assert len(bars) == 1
    assert bars[0]["close"] == 10.5


def test_ohlcv_endpoint_requires_auth():
    resp = _client().get("/api/v1/market-data/ohlcv?symbol=BTCUSDT")
    assert resp.status_code in (401, 403)


def test_order_book_endpoint_reports_unavailable_when_no_data():
    symbol = f"MDNOBOOK{uuid4().hex[:6]}"
    resp = _client().get(
        f"/api/v1/market-data/order-book?symbol={symbol}",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_agents_endpoint_lists_real_registered_domains():
    resp = _client().get("/api/v1/agents/", headers=make_authed_headers(Role.VIEWER))
    assert resp.status_code == 200
    data = resp.json()
    domains = {a["domain"] for a in data["agents"]}
    assert {"technical", "macro", "sentiment", "onchain", "pattern", "quant", "order_flow", "time", "epistemology"} <= domains
    critic_domains = {c["domain"] for c in data["critics"]}
    assert "risk" in critic_domains
    assert "alter_ego" in critic_domains
