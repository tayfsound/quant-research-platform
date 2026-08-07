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
        "leverage": row.get("leverage"),
        "liquidation_price": row.get("liquidation_price"),
        "timeframe": row.get("timeframe"),
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
    """Faz 224: kritik bulgu — "summary" artık `limit`'e (tablo için kaç
    satır gösterileceği) bağlı DEĞİL, gerçek toplam üzerinden hesaplanıyor
    (closed_trades_summary — /performance'ın all_time'ıyla AYNI sorgu).
    `trades` listesi hâlâ `limit` ile sınırlı (tabloyu 10 binlerce satır
    render etmemek için) ama bu artık sadece görüntüleme sınırı, istatistik
    kaynağı değil."""
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        rows = persistor.list_closed_trades(limit=limit)
        trades = [_serialize(r) for r in rows]
        summary = persistor.closed_trades_summary()
        return {
            "trades": trades,
            "summary": {
                "count": summary["trade_count"],
                "win_rate": summary["win_rate"],
                "total_pnl": summary["total_pnl"],
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
            result = []
            for r in rows:
                deployed = float(r["deployed_notional"] or 0.0)
                total_pnl = float(r["total_pnl"] or 0.0)
                result.append({
                    "period_start": r["bucket"].isoformat(),
                    "trade_count": r["trade_count"],
                    "total_pnl": total_pnl,
                    "win_rate": (r["wins"] / r["trade_count"]) if r["trade_count"] else 0.0,
                    "roi_pct": (total_pnl / starting_capital) if starting_capital else 0.0,
                    # Faz 215: kullanıcı bulgusu — starting_capital test
                    # amaçlı çok büyük bir sayıya çekilince (ör. 10 milyar),
                    # roi_pct her zaman ~0'a yuvarlanıyor, kazanma oranı ve
                    # PnL negatifken bile — kafa karıştırıcı görünüyordu.
                    # Bu, GERÇEKTEN kullanılan sermayeye (bu dönemde açılan
                    # işlemlerin toplam notional'ı) göre getiri — kasa
                    # büyüklüğünden bağımsız, stratejinin kendi
                    # performansını yansıtıyor.
                    "roi_pct_on_deployed": (total_pnl / deployed) if deployed else 0.0,
                })
            return result

        daily = _bucket(persistor.performance_by_period("day"))
        weekly = _bucket(persistor.performance_by_period("week"))
        monthly = _bucket(persistor.performance_by_period("month"))
        yearly = _bucket(persistor.performance_by_period("year"))

        # Faz 224: kritik bulgu — burası önceden list_closed_trades(limit=
        # 10000) ile Python'da topluyordu, GET /trades ise limit=100 ile
        # ayrı bir hesap yapıyordu — kullanıcının "işlem sayısı 100
        # görünüyor, Performance'da farklıydı" şikayetinin kök nedeni.
        # Artık ikisi de AYNI, limitsiz SQL agregasyonunu (closed_trades_
        # summary) kullanıyor — tek gerçek kaynak.
        summary = persistor.closed_trades_summary()
        total_pnl = summary["total_pnl"]
        deployed_notional = summary["deployed_notional"]

        return {
            "starting_capital": starting_capital,
            "all_time": {
                "trade_count": summary["trade_count"],
                "total_pnl": total_pnl,
                "win_rate": summary["win_rate"],
                "roi_pct": (total_pnl / starting_capital) if starting_capital else 0.0,
                "roi_pct_on_deployed": (total_pnl / deployed_notional) if deployed_notional else 0.0,
                "deployed_notional": deployed_notional,
                # Faz 238: kullanıcı isteği — "kirli geçmiş veriyi
                # temizle." Aşırı-capital test döneminden kalan, gerçek
                # olmayan notional'lı işlemler (excluded_from_stats=true)
                # istatistiklerden hariç tutuluyor — silinmiyor, sadece
                # şeffaflık için kaç tanesinin hariç tutulduğu gösteriliyor.
                "excluded_dirty_trades_count": summary["excluded_count"],
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
