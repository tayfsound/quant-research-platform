"""Market Data read API — dashboard'un Market Overview grafiği için.

Faz 184'te eklenen market_snapshots tablosunu okur (IngestionPipeline
tarafından gerçek Binance verisiyle dolduruluyor)."""
from fastapi import APIRouter, Depends

from contracts.market_data import DataSource, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
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
