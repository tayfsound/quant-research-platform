"""Faz 187: gerçek açık pozisyon / kapanmış işlem (paper trading) API.

Binance tarzı "my trades" görünümü için gerekli tek gerçek kaynak — decisions
tablosundaki status='open'/'closed' satırları, services/position_closer.py
tarafından gerçek zaman geçtikten sonra gerçek fiyatla kapatılıyor."""
from fastapi import APIRouter, Depends

from contracts.auth import Role
from database.repositories.app_settings_repository import (
    TRADE_HORIZON_SECONDS,
    AppSettingsRepository,
)
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import RoutingProvider
from services.auth_service import AuthContext, get_current_user, require_role
from services.position_closer import PositionCloser

router = APIRouter(tags=["positions"])


def _serialize(row: dict) -> dict:
    outcome = row.get("outcome") or {}
    return {
        "id": str(row["id"]),
        "symbol": row["symbol"],
        "direction": row["direction"],
        "entry_price": row.get("entry_price"),
        "exit_price": row.get("exit_price"),
        "quantity": row.get("quantity"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "pnl": row.get("pnl"),
        "stop_loss_price": row.get("stop_loss_price"),
        "take_profit_price": row.get("take_profit_price"),
        "exit_reason": outcome.get("exit_reason"),
        "opened_at": row["opened_at"].isoformat() if row.get("opened_at") else None,
        "closed_at": row["closed_at"].isoformat() if row.get("closed_at") else None,
    }


@router.get("/positions")
async def list_open_positions(limit: int = 100, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).list_open_positions(limit=limit)
        return {"positions": [_serialize(r) for r in rows]}


@router.get("/trades")
async def list_closed_trades(limit: int = 100, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).list_closed_trades(limit=limit)
        trades = [_serialize(r) for r in rows]
        wins = [t for t in trades if (t.get("pnl") or 0) > 0]
        return {
            "trades": trades,
            "summary": {
                "count": len(trades),
                "win_rate": (len(wins) / len(trades)) if trades else 0.0,
                "total_pnl": sum(t.get("pnl") or 0 for t in trades),
            },
        }


@router.get("/performance")
async def performance_summary(user: AuthContext = Depends(get_current_user)):
    """Faz 215: kullanıcı isteği — "dün ne kadar ROI yapmış, haftalık/
    aylık/yıllık ne olmuş" görebilmek. ROI, kullanıcının Settings'te
    belirlediği starting_capital'a göre (gerçek referans sermaye,
    icat edilmiş bir sayı değil)."""
    with SessionFactory.get_session() as session:
        starting_capital = float(AppSettingsRepository(session).get("starting_capital"))
        persistor = DecisionPersistor(session)

        def _bucket(rows):
            return [
                {
                    "period_start": r["bucket"].isoformat(),
                    "trade_count": r["trade_count"],
                    "total_pnl": float(r["total_pnl"] or 0.0),
                    "win_rate": (r["wins"] / r["trade_count"]) if r["trade_count"] else 0.0,
                    "roi_pct": (float(r["total_pnl"] or 0.0) / starting_capital) if starting_capital else 0.0,
                }
                for r in rows
            ]

        daily = _bucket(persistor.performance_by_period("day"))
        weekly = _bucket(persistor.performance_by_period("week"))
        monthly = _bucket(persistor.performance_by_period("month"))
        yearly = _bucket(persistor.performance_by_period("year"))

        all_closed = persistor.list_closed_trades(limit=10000)
        total_pnl = sum(t.get("pnl") or 0.0 for t in all_closed)
        wins = sum(1 for t in all_closed if (t.get("pnl") or 0) > 0)

        return {
            "starting_capital": starting_capital,
            "all_time": {
                "trade_count": len(all_closed),
                "total_pnl": total_pnl,
                "win_rate": (wins / len(all_closed)) if all_closed else 0.0,
                "roi_pct": (total_pnl / starting_capital) if starting_capital else 0.0,
            },
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "yearly": yearly,
        }


@router.post("/positions/close-due")
async def close_due_positions(
    hold_seconds: int | None = None,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Prod'da celery beat periyodik çalıştırır (close_due_positions_task);
    bu endpoint manuel tetikleme ve test için. hold_seconds verilmezse
    kullanıcının Settings'te seçtiği trade_horizon kullanılır."""
    if hold_seconds is None:
        with SessionFactory.get_session() as session:
            horizon = AppSettingsRepository(session).get("trade_horizon")
        hold_seconds = TRADE_HORIZON_SECONDS.get(horizon, 600)

    closer = PositionCloser(RoutingProvider(), hold_seconds=hold_seconds)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))
    return {"closed_count": len(closed), "closed": closed}
