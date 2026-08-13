"""Liquidity-Adjusted VaR API.

analytics/liquidity_adjusted_var.py gerçek zamanlı çağrılır. Her açık
pozisyonun sembolü için: fiyat VaR'ı GERÇEK geçmiş getirilerin std'sinden
(Binance), likidite maliyeti GERÇEK order_book_snapshots.spread_bps
geçmişinden hesaplanıyor. Binance'te olmayan semboller fail-closed
sessizce atlanıyor."""
import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import text

from analytics.liquidity_adjusted_var import DEFAULT_Z_SCORE, compute_liquidity_adjusted_var
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.real_returns import fetch_symbol_returns
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/liquidity-var", tags=["liquidity-var"])


@router.get("/")
async def liquidity_var(
    timeframe: str = "1h",
    bars_count: int = 200,
    spread_lookback_hours: int = 24,
    z_score: float = DEFAULT_Z_SCORE,
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        open_positions = DecisionPersistor(session).list_open_positions(limit=5000)

        notional_by_symbol: dict[str, float] = {}
        for pos in open_positions:
            sym = pos["symbol"]
            notional = float(pos["entry_price"] or 0) * float(pos["quantity"] or 0)
            notional_by_symbol[sym] = notional_by_symbol.get(sym, 0.0) + notional

        results = {}
        for sym, notional in notional_by_symbol.items():
            if notional <= 0:
                continue
            try:
                rets = await fetch_symbol_returns(sym, timeframe, bars_count)
            except Exception:
                continue  # Binance'te yok (ör. GC=F/SI=F) — fail-closed atla
            if len(rets) < 2:
                continue
            price_var = z_score * float(np.std(rets)) * notional

            spread_rows = session.execute(
                text("""
                    SELECT spread_bps FROM order_book_snapshots
                    WHERE symbol = :symbol AND time > now() - (:hours || ' hours')::interval
                        AND spread_bps IS NOT NULL
                    ORDER BY time DESC
                """),
                {"symbol": sym, "hours": spread_lookback_hours},
            ).fetchall()
            spread_series = [float(r[0]) for r in spread_rows]

            results[sym] = {
                "notional": round(notional, 2),
                **compute_liquidity_adjusted_var(price_var, spread_series, notional, z_score),
            }

    return {"positions": results}
