"""Faz 187: gerçek açık pozisyon / kapanmış işlem (paper trading) API.

Binance tarzı "my trades" görünümü için gerekli tek gerçek kaynak — decisions
tablosundaki status='open'/'closed' satırları, services/position_closer.py
tarafından gerçek zaman geçtikten sonra gerçek fiyatla kapatılıyor."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from contracts.auth import Role
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.data_provider import RoutingProvider
from services.auth_service import AuthContext, get_current_user, require_role
from services.position_closer import PositionCloser

router = APIRouter(tags=["positions"])


def _serialize(row: dict, current_price: float | None = None, net_unrealized_pnl: float | None = None) -> dict:
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
        "realized_pnl": outcome.get("realized_pnl"),
        # Faz 268p — kullanıcı isteği: "pozisyon o an karda mı zararda mı
        # göremiyorum." current_price/net_unrealized_pnl SADECE açık
        # pozisyonlar için (GET /positions'tan) dolduruluyor — komisyon
        # düşülmüş, "şimdi kapatsam cebe ne geçer" rakamı (services/
        # position_closer.py::estimate_net_pnl_if_closed_now ile AYNI
        # formül, toplu-kapatma kararıyla asla çelişmesin diye).
        "current_price": current_price,
        "net_unrealized_pnl": net_unrealized_pnl,
        "opened_at": row["opened_at"].isoformat() if row.get("opened_at") else None,
        "closed_at": row["closed_at"].isoformat() if row.get("closed_at") else None,
    }


def _fetch_current_prices(symbols: set[str]) -> dict[str, float]:
    """Faz 268p: her benzersiz sembol için TEK bir fiyat çekiyor (100'lerce
    pozisyon aynı ~10-15 watchlist sembolünü paylaşıyor) — pozisyon başına
    değil, sembol başına bir istek. Bir sembol çekilemezse (fail-closed)
    sadece o sembol sözlükte hiç yer almaz, diğerleri etkilenmez."""
    provider = RoutingProvider()
    prices: dict[str, float] = {}
    for symbol in symbols:
        try:
            data = provider.get_ohlcv(symbol, "1m", limit=1)
            if data:
                prices[symbol] = data[-1].close
        except Exception:
            continue
    return prices


@router.get("/positions")
async def list_open_positions(limit: int = 100, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        rows = persistor.list_open_positions(limit=limit)
        summary = persistor.open_positions_summary()

    prices = _fetch_current_prices({r["symbol"] for r in rows})
    closer = PositionCloser(RoutingProvider())
    positions = []
    for r in rows:
        price = prices.get(r["symbol"])
        net_pnl = closer.estimate_net_pnl_if_closed_now(r, price) if price is not None else None
        positions.append(_serialize(r, current_price=price, net_unrealized_pnl=net_pnl))

    return {
        "positions": positions,
        "summary": summary,
    }


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
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Prod'da celery beat periyodik çalıştırır (close_due_positions_task);
    bu endpoint manuel tetikleme ve test için. Faz 265: hold_seconds
    parametresi kaldırıldı — Faz 215'ten beri PositionCloser bunu zaten
    hiç kullanmıyordu (pozisyonlar sadece gerçekten stop/hedefe/
    likidasyona ulaşınca kapanıyor, süre yüzünden asla)."""
    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))
    return {"closed_count": len(closed), "closed": closed}


class PartialCloseRequest(BaseModel):
    fraction: float


@router.post("/positions/{decision_id}/partial-close")
async def partial_close_position(
    decision_id: str,
    body: PartialCloseRequest,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 268 — kullanıcı isteği: "aşamalı kapama, pozisyonun yarısını/
    çeyreğini kademeli kapatabilen mekanizma." fraction=0.5 açık miktarın
    yarısını, 0.25 çeyreğini gerçek güncel fiyattan realize eder; pozisyon
    'open' kalır, sadece quantity azalır. fraction=1.0 kalanın tamamını
    kapatır (gerçek bir tam kapanış)."""
    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        try:
            result = closer.close_partial(DecisionPersistor(session), decision_id, body.fraction)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    return result


@router.post("/positions/close-profitable")
async def close_profitable_positions(
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 268p — kullanıcı isteği: "kârda olan pozisyonları toplu kapatma
    butonu... komisyona ezilmeyecek şekilde karda ise kapansınlar."
    Kapatmadan ÖNCE her pozisyon için güncel fiyatla net (komisyon
    düşülmüş) kâr tahmini hesaplanır — SADECE pozitif çıkanlar gerçekten
    kapatılır. Kapanış işlemi geri alınamaz olduğu için (services/
    position_closer.py::close_partial fraction=1.0 çağrısı DB'yi hemen
    günceller), önce filtrelemek zorunlu — "kapat, zarardaysa geri al"
    diye bir şey yok. Görünen sayfa (limit=100) ile sınırlı DEĞİL — TÜM
    açık pozisyonlar taranır."""
    closer = PositionCloser(RoutingProvider())
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        positions = persistor.list_open_positions(limit=100_000)

    prices = _fetch_current_prices({p["symbol"] for p in positions})

    closed = []
    skipped_unprofitable = 0
    skipped_no_price = 0
    for pos in positions:
        price = prices.get(pos["symbol"])
        if price is None:
            skipped_no_price += 1
            continue
        estimated_net_pnl = closer.estimate_net_pnl_if_closed_now(pos, price)
        if estimated_net_pnl <= 0:
            skipped_unprofitable += 1
            continue

        with SessionFactory.get_session() as session:
            try:
                result = closer.close_partial(DecisionPersistor(session), str(pos["id"]), 1.0)
            except ValueError:
                continue
        closed.append({"decision_id": str(pos["id"]), "symbol": pos["symbol"], "pnl": result["pnl"]})

    return {
        "closed_count": len(closed),
        "closed": closed,
        "skipped_unprofitable": skipped_unprofitable,
        "skipped_no_price": skipped_no_price,
    }
