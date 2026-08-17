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


def test_ohlcv_endpoint_falls_back_to_real_yahoo_data_for_non_crypto_symbols_with_no_db_rows():
    """Faz 215: kullanıcı bulgusu — Market sayfasında Nasdaq/hisse/emtia
    sembolleri için grafik hiç açılmıyordu. Kök neden: market_snapshots
    tablosu sadece Binance sembolleri için besleniyor. AAPL gibi bir
    sembol için DB'de hiç satır yok — artık gerçek Yahoo Finance
    çağrısına düşüyor (RoutingProvider'ın trading pipeline'ında zaten
    yaptığı gibi)."""
    resp = _client().get(
        "/api/v1/market-data/ohlcv?symbol=AAPL&resolution=1d&limit=5",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert resp.status_code == 200
    bars = resp.json()["bars"]
    assert len(bars) > 0
    assert bars[-1]["close"] > 0


def test_ohlcv_endpoint_falls_back_to_real_binance_data_for_off_watchlist_crypto_symbols():
    """Kullanıcı bulgusu: pump_fade_strategy.py watchlist'ten bağımsız TÜM
    USDT-perpetual evrenini tarıyor, PORTALUSDT gibi bir sembolde gerçek
    işlem açabiliyor — ama ingest_candles_task SADECE watchlist'i besliyor,
    yani market_snapshots'ta bu sembol için hiç satır yok. Eski kod SADECE
    non-crypto sembollerde Yahoo'ya düşüyordu; crypto ama DB'de verisi
    olmayan semboller sessizce boş bars döndürüyordu. Artık looks_like_
    binance_pair olan ama DB'de satırı olmayan semboller de RoutingProvider
    ile gerçek Binance'a düşüyor."""
    resp = _client().get(
        "/api/v1/market-data/ohlcv?symbol=PORTALUSDT&resolution=1h&limit=5",
        headers=make_authed_headers(Role.VIEWER),
    )
    assert resp.status_code == 200
    bars = resp.json()["bars"]
    assert len(bars) > 0
    assert bars[-1]["close"] > 0


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


def test_news_sentiment_endpoint_reports_unavailable_when_cache_empty(monkeypatch):
    import market_data.sentiment.llm_news_sentiment_provider as provider

    monkeypatch.setattr(provider, "get_cached", lambda: (None, None))
    resp = _client().get("/api/v1/market-data/news-sentiment", headers=make_authed_headers(Role.VIEWER))
    assert resp.status_code == 200
    assert resp.json() == {"available": False}


def test_news_sentiment_endpoint_returns_cached_score_and_summary(monkeypatch):
    import market_data.sentiment.llm_news_sentiment_provider as provider

    monkeypatch.setattr(provider, "get_cached", lambda: (0.42, "Piyasa olumlu."))
    resp = _client().get("/api/v1/market-data/news-sentiment", headers=make_authed_headers(Role.VIEWER))
    assert resp.status_code == 200
    assert resp.json() == {"available": True, "sentiment_score": 0.42, "summary": "Piyasa olumlu."}


def test_news_sentiment_endpoint_requires_auth():
    resp = _client().get("/api/v1/market-data/news-sentiment")
    assert resp.status_code in (401, 403)


def test_agents_endpoint_lists_real_registered_domains():
    resp = _client().get("/api/v1/agents/", headers=make_authed_headers(Role.VIEWER))
    assert resp.status_code == 200
    data = resp.json()
    domains = {a["domain"] for a in data["agents"]}
    assert {"technical", "macro", "sentiment", "onchain", "pattern", "quant", "order_flow", "time", "epistemology"} <= domains
    critic_domains = {c["domain"] for c in data["critics"]}
    assert "risk" in critic_domains
    assert "alter_ego" in critic_domains
