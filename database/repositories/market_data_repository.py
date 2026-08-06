"""Market Data repository — Market Data Service sprint.

`contracts/market_data.py::MarketSnapshot` zaten tam olarak bu iş için
tasarlanmıştı (time/exchange/symbol/resolution/OHLCV/quality) ama hiçbir
repository onu kalıcı kılmıyordu — bu, o eksik parça.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from contracts.market_data import DataQuality, DataSource, MarketSnapshot, Resolution


class MarketDataRepository:
    def __init__(self, session):
        self.session = session

    def upsert_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Aynı (exchange, symbol, resolution, time) tekrar gelirse
        (örn. henüz kapanmamış bir mumun güncellenmesi) günceller,
        duplicate satır oluşturmaz."""
        self.session.execute(
            text("""
                INSERT INTO market_snapshots
                    (exchange, symbol, resolution, time, open, high, low, close, volume, source_version, quality)
                VALUES
                    (:exchange, :symbol, :resolution, :time, :open, :high, :low, :close, :volume, :source_version, :quality)
                ON CONFLICT (exchange, symbol, resolution, time) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    source_version = EXCLUDED.source_version,
                    quality = EXCLUDED.quality
            """),
            {
                "exchange": snapshot.exchange.value,
                "symbol": snapshot.symbol,
                "resolution": snapshot.resolution.value,
                "time": snapshot.time,
                "open": snapshot.open,
                "high": snapshot.high,
                "low": snapshot.low,
                "close": snapshot.close,
                "volume": snapshot.volume,
                "source_version": snapshot.source_version,
                "quality": snapshot.quality.value,
            },
        )
        self.session.commit()

    def upsert_snapshots(self, snapshots: list[MarketSnapshot]) -> int:
        for snapshot in snapshots:
            self.upsert_snapshot(snapshot)
        return len(snapshots)

    def get_latest_snapshots(
        self,
        exchange: DataSource,
        symbol: str,
        resolution: Resolution,
        limit: int = 100,
    ) -> list[MarketSnapshot]:
        rows = self.session.execute(
            text("""
                SELECT * FROM market_snapshots
                WHERE exchange = :exchange AND symbol = :symbol AND resolution = :resolution
                ORDER BY time DESC
                LIMIT :limit
            """),
            {"exchange": exchange.value, "symbol": symbol, "resolution": resolution.value, "limit": limit},
        ).mappings().all()

        # En eski -> en yeni sırayla dön (OHLCVProvider'ın/backtest'in
        # zaten beklediği sıra — mock_adapter.generate() de aynı sırayı verir).
        return [self._row_to_snapshot(r) for r in reversed(rows)]

    def _row_to_snapshot(self, row) -> MarketSnapshot:
        return MarketSnapshot(
            time=row["time"],
            exchange=DataSource(row["exchange"]),
            symbol=row["symbol"],
            resolution=Resolution(row["resolution"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            source_version=row["source_version"],
            quality=DataQuality(row["quality"]),
        )

    def save_trade(
        self,
        *,
        exchange: DataSource,
        symbol: str,
        price: float,
        quantity: float,
        time: datetime,
        side: str | None = None,
        trade_id: UUID | None = None,
    ) -> None:
        self.session.execute(
            text("""
                INSERT INTO market_trades (id, time, exchange, symbol, price, quantity, side)
                VALUES (:id, :time, :exchange, :symbol, :price, :quantity, :side)
            """),
            {
                "id": str(trade_id or uuid4()),
                "time": time,
                "exchange": exchange.value,
                "symbol": symbol,
                "price": price,
                "quantity": quantity,
                "side": side,
            },
        )
        self.session.commit()

    def get_recent_trades(self, symbol: str, limit: int = 100) -> list[dict]:
        rows = self.session.execute(
            text("""
                SELECT * FROM market_trades
                WHERE symbol = :symbol
                ORDER BY time DESC
                LIMIT :limit
            """),
            {"symbol": symbol, "limit": limit},
        ).mappings().all()
        return [dict(r) for r in rows]

    def save_order_book_snapshot(
        self,
        *,
        exchange: DataSource,
        symbol: str,
        time: datetime,
        best_bid: float,
        best_ask: float,
        bid_volume: float,
        ask_volume: float,
        imbalance: float,
        spread_bps: float,
        aggressive_buy_ratio: float | None = None,
    ) -> None:
        self.session.execute(
            text("""
                INSERT INTO order_book_snapshots
                    (exchange, symbol, time, best_bid, best_ask, bid_volume, ask_volume, imbalance, spread_bps, aggressive_buy_ratio)
                VALUES
                    (:exchange, :symbol, :time, :best_bid, :best_ask, :bid_volume, :ask_volume, :imbalance, :spread_bps, :aggressive_buy_ratio)
            """),
            {
                "exchange": exchange.value,
                "symbol": symbol,
                "time": time,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "imbalance": imbalance,
                "spread_bps": spread_bps,
                "aggressive_buy_ratio": aggressive_buy_ratio,
            },
        )
        self.session.commit()

    def get_latest_order_book_snapshot(self, exchange: DataSource, symbol: str) -> dict | None:
        row = self.session.execute(
            text("""
                SELECT * FROM order_book_snapshots
                WHERE exchange = :exchange AND symbol = :symbol
                ORDER BY time DESC LIMIT 1
            """),
            {"exchange": exchange.value, "symbol": symbol},
        ).mappings().first()
        return dict(row) if row else None
