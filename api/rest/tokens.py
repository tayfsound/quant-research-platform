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
from market_data.market_hours import is_market_open
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/tokens", tags=["tokens"])


def _price_from_decision(decision: dict | None) -> float | None:
    """Faz 211: gerçek bulgu — kripto olmayan semboller (NVDA/AAPL/^IXIC/
    GC=F/SI=F gibi) için Tokens sayfasında fiyat hiç görünmüyordu, çünkü
    market_snapshots tablosu (Faz 207) sadece Binance'a özel. Her gerçek
    council cycle'ı zaten kendi anlık fiyatını (agent_contributions'taki
    market_snapshot girdisi) taşıyor — asset sınıfından bağımsız, ekstra
    bir API çağrısı gerektirmeden buradan okunabilir."""
    if not decision:
        return None
    for item in decision.get("agent_contributions") or []:
        if item.get("type") == "market_snapshot":
            return (item.get("data") or {}).get("raw_snapshot", {}).get("close")
    return None


def _latest_price(session, symbol: str, latest_decision: dict | None) -> float | None:
    price = _price_from_decision(latest_decision)
    if price is not None:
        return price
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
                "price": _latest_price(session, symbol, latest),
                "direction": latest["direction"] if latest else None,
                "confidence": float(latest["confidence"]) if latest and latest["confidence"] is not None else None,
                "size": float(latest["size"]) if latest and latest["size"] is not None else None,
                "status": latest["status"] if latest else None,
                "updated_at": latest["timestamp"].isoformat() if latest else None,
                # Faz 212: kullanıcı NVDA/AAPL/^IXIC gibi hisse/endeks
                # sembollerinde hiç veri görmeyince bunu bug sandı — gerçek
                # sebep piyasa saatleri dışında bu sembollerin cycle'a hiç
                # girmemesi (run_trading_cycle_task açıkça atlıyor). Şimdi
                # bu ayrım UI'da da görünür.
                "market_open": is_market_open(symbol),
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
            "price": _latest_price(session, symbol, decisions[0] if decisions else None),
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
                    "opened_at": d["opened_at"].isoformat() if d.get("opened_at") else None,
                    "closed_at": d["closed_at"].isoformat() if d.get("closed_at") else None,
                    # Faz 210: giriş/çıkış saatleri ve kapanış sebebi
                    # (take_profit/stop_loss/time_expired) dashboard'da hiç
                    # görünmüyordu — kullanıcı "hedef vurdu ama net zarar"
                    # gibi durumları backend'e sormadan anlayamıyordu.
                    "exit_reason": (d.get("outcome") or {}).get("exit_reason"),
                }
                for d in decisions
            ],
        }
