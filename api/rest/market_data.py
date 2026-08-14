"""Market Data read API — dashboard'un Market Overview grafiği için.

Faz 184'te eklenen market_snapshots tablosunu okur (IngestionPipeline
tarafından gerçek Binance verisiyle dolduruluyor)."""
from fastapi import APIRouter, Depends

from contracts.market_data import DataSource, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import looks_like_binance_pair
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = "BTCUSDT",
    resolution: str = "1m",
    limit: int = 200,
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        rows = MarketDataRepository(session).get_latest_snapshots(
            DataSource.BINANCE, symbol, Resolution(resolution), limit=limit
        )

    # Faz 215: gerçek bulgu — market_snapshots tablosu SADECE Binance
    # sembolleri için besleniyor (ingest_candles_task kripto-filtreli).
    # Hisse/endeks/emtia (AAPL/NVDA/^IXIC/GC=F) için bu tabloda hiçbir
    # zaman satır olmuyordu — Market sayfasında grafik hep boş kalıyordu.
    # Gerçek trading pipeline'ının zaten yaptığı gibi (RoutingProvider),
    # kripto olmayan ve DB'de hiç verisi olmayan semboller için canlı
    # Yahoo Finance çağrısına düşülüyor — ayrı bir ingestion/depolama
    # hattı kurmaya gerek yok, Yahoo verisi zaten anlık ve hızlı.
    if not rows and not looks_like_binance_pair(symbol):
        from market_data.ingestion.yahoo_provider import YahooProvider

        bars = YahooProvider().get_ohlcv(symbol, resolution, limit=limit)
        return {
            "symbol": symbol,
            "resolution": resolution,
            "bars": [
                {
                    "time": int(b.timestamp.timestamp()),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ],
        }

    return {
        "symbol": symbol,
        "resolution": resolution,
        "bars": [
            {
                "time": int(r.time.timestamp()),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ],
    }


@router.get("/news-sentiment")
async def get_news_sentiment(user: AuthContext = Depends(get_current_user)):
    """Faz 268-sonrası: Reddit'in yerine geçen LLM tabanlı gerçek haber
    sentiment'i (bkz. market_data/sentiment/llm_news_sentiment_provider.py).
    SADECE önbelleği okur (asla burada LLM çağırmaz) — periyodik Celery
    görevi (refresh_llm_news_sentiment_task) ayrı olarak tazeler.
    Hiç tazelenmemişse/süresi dolmuşsa available=False, uydurulmuş bir
    skor/özet asla döndürülmez."""
    from market_data.sentiment.llm_news_sentiment_provider import get_cached

    score, summary = get_cached()
    if score is None:
        return {"available": False}
    return {"available": True, "sentiment_score": score, "summary": summary}


@router.get("/order-book")
async def get_order_book_snapshot(
    symbol: str = "BTCUSDT",
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        row = MarketDataRepository(session).get_latest_order_book_snapshot(DataSource.BINANCE, symbol)
        if not row:
            return {"symbol": symbol, "available": False}
        return {
            "symbol": symbol,
            "available": True,
            "best_bid": row["best_bid"],
            "best_ask": row["best_ask"],
            "bid_volume": row["bid_volume"],
            "ask_volume": row["ask_volume"],
            "imbalance": row["imbalance"],
            "spread_bps": row["spread_bps"],
            "time": row["time"].isoformat(),
        }
