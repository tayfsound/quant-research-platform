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
def get_ohlcv(
    symbol: str = "BTCUSDT",
    resolution: str = "1m",
    limit: int = 200,
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        rows = MarketDataRepository(session).get_latest_snapshots(
            DataSource.BINANCE, symbol, Resolution(resolution), limit=limit
        )

    # Faz 215: gerçek bulgu — market_snapshots tablosu SADECE watchlist'teki
    # Binance sembolleri için besleniyor (ingest_candles_task watchlist'e
    # sabit). Hisse/endeks/emtia (AAPL/NVDA/^IXIC/GC=F) için bu tabloda
    # hiçbir zaman satır olmuyordu — Market sayfasında grafik hep boş
    # kalıyordu. Kripto olmayan semboller için canlı Yahoo Finance
    # çağrısına düşülüyordu.
    #
    # Kullanıcı bulgusu (sonraki bulgu): AYNI boşluk watchlist DIŞI kripto
    # semboller için de vardı — pump_fade_strategy.py watchlist'ten
    # bağımsız TÜM USDT-perpetual evrenini tarıyor (bkz. api/rest/
    # positions.py), yani PORTALUSDT gibi bir sembolde gerçek bir işlem
    # açılabiliyor ama grafiği hiç çekilemiyordu (looks_like_binance_pair
    # doğru olduğu için Yahoo'ya da düşmüyordu, market_snapshots'ta da
    # hiç satırı yoktu — sessizce boş bars döndürüyordu). RoutingProvider
    # zaten sembol tipine göre doğru borsaya yönlendiriyor (gerçek trading
    # pipeline'ının kullandığı AYNI sınıf) — DB'de veri yoksa artık HER
    # sembol için canlı çağrıya düşülüyor, ayrı bir ingestion hattı
    # kurmaya gerek yok.
    if not rows:
        if looks_like_binance_pair(symbol):
            from market_data.ingestion.data_provider import RoutingProvider
            provider = RoutingProvider()
        else:
            from market_data.ingestion.yahoo_provider import YahooProvider
            provider = YahooProvider()

        bars = provider.get_ohlcv(symbol, resolution, limit=limit)
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


@router.get("/order-book")
def get_order_book_snapshot(
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
