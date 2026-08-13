"""Correlation Breakdown Detection API.

analytics/correlation_breakdown.py gerçek zamanlı çağrılır — watchlist'teki
her sembol için GERÇEK geçmiş kapanış fiyatlarından (Binance) dönemsel
getiri serisi çekilip hizalanıyor. Binance'te bulunmayan semboller (ör.
GC=F, SI=F — yfinance kaynaklı) fail-closed olarak sessizce atlanıyor,
uç nokta hata vermiyor."""
from fastapi import APIRouter, Depends

from analytics.correlation_breakdown import compute_correlation_breakdown
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from exchange_gateway.binance.adapter import BinanceAdapter
from market_data.ingestion.ohlcv import from_binance_klines
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/correlation-breakdown", tags=["correlation-breakdown"])


async def _fetch_returns(symbol: str, timeframe: str, limit: int) -> list[float]:
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        raw = await adapter.fetch_ohlcv(symbol, timeframe, limit=limit)
    finally:
        await adapter.disconnect()
    bars = from_binance_klines(raw)
    closes = [b.close for b in bars]
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes)) if closes[i - 1]
    ]


@router.get("/")
async def correlation_breakdown(
    timeframe: str = "1h",
    bars_count: int = 200,
    baseline_window: int = 100,
    recent_window: int = 50,
    user: AuthContext = Depends(get_current_user),
):
    with SessionFactory.get_session() as session:
        watchlist = AppSettingsRepository(session).get("watchlist")
    symbols = [s.strip() for s in watchlist.split(",") if s.strip()]

    returns: dict[str, list[float]] = {}
    for sym in symbols:
        try:
            rets = await _fetch_returns(sym, timeframe, bars_count)
        except Exception:
            continue
        if len(rets) >= baseline_window + recent_window:
            returns[sym] = rets

    return {
        "pairs": compute_correlation_breakdown(returns, baseline_window, recent_window),
        "symbols_evaluated": list(returns.keys()),
    }
