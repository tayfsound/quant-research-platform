"""Faz 207: Tokens API — dashboard'da AI'ın izlediği watchlist'in tamamını
tek ekranda göstermek için. Gerçek bulgu: Predictions.tsx sadece tek bir
(varsayılan) sembolü gösteriyordu, watchlist 15 kaleme çıktıktan sonra bile
kullanıcının geri kalan 14 sembol hakkında hiçbir görünürlüğü yoktu."""
from fastapi import APIRouter, Depends, HTTPException

from contracts.market_data import DataSource, Resolution
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import looks_like_binance_pair
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/tokens", tags=["tokens"])


def _latest_price(session, symbol: str) -> float | None:
    if not looks_like_binance_pair(symbol):
        return None
    snapshots = MarketDataRepository(session).get_latest_snapshots(
        DataSource.BINANCE, symbol, Resolution("1m"), limit=1
    )
    return snapshots[-1].close if snapshots else None


@router.get("/")
async def list_tokens(user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        watchlist = [
            s.strip() for s in AppSettingsRepository(session).get("watchlist").split(",") if s.strip()
        ]
        persistor = DecisionPersistor(session)

        tokens = []
        for symbol in watchlist:
            recent = persistor.get_by_symbol(symbol, limit=1)
            latest = recent[0] if recent else None
            tokens.append({
                "symbol": symbol,
                "is_crypto": looks_like_binance_pair(symbol),
                "price": _latest_price(session, symbol),
                "direction": latest["direction"] if latest else None,
                "confidence": float(latest["confidence"]) if latest and latest["confidence"] is not None else None,
                "size": float(latest["size"]) if latest and latest["size"] is not None else None,
                "status": latest["status"] if latest else None,
                "updated_at": latest["timestamp"].isoformat() if latest else None,
            })

        return {"tokens": tokens}


@router.get("/{symbol}")
async def token_detail(symbol: str, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        watchlist = [
            s.strip() for s in AppSettingsRepository(session).get("watchlist").split(",") if s.strip()
        ]
        if symbol not in watchlist:
            raise HTTPException(404, f"{symbol} is not in the current watchlist")

        persistor = DecisionPersistor(session)
        decisions = persistor.get_by_symbol(symbol, limit=30)

        order_book = None
        if looks_like_binance_pair(symbol):
            row = MarketDataRepository(session).get_latest_order_book_snapshot(DataSource.BINANCE, symbol)
            if row:
                order_book = {
                    "best_bid": row["best_bid"],
                    "best_ask": row["best_ask"],
                    "imbalance": row["imbalance"],
                    "spread_bps": row["spread_bps"],
                    "time": row["time"].isoformat(),
                }

        return {
            "symbol": symbol,
            "is_crypto": looks_like_binance_pair(symbol),
            "price": _latest_price(session, symbol),
            "order_book": order_book,
            "decisions": [
                {
                    "id": str(d["id"]),
                    "timestamp": d["timestamp"].isoformat(),
                    "direction": d["direction"],
                    "confidence": float(d["confidence"]) if d["confidence"] is not None else None,
                    "size": float(d["size"]) if d["size"] is not None else None,
                    "status": d["status"],
                    "pnl": float(d["pnl"]) if d.get("pnl") is not None else None,
                    "entry_price": d.get("entry_price"),
                    "exit_price": d.get("exit_price"),
                }
                for d in decisions
            ],
        }
