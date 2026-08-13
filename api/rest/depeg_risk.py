"""Stablecoin/Pegged-Asset Depeg Risk API.

analytics/depeg_risk.py gerçek zamanlı çağrılır. XAUTUSDT/PAXGUSDT'nin
GERÇEK spot altına (GC=F, Yahoo Finance) göre, USDCUSDT'nin GERÇEK 1.00
USD referansına göre ne kadar saptığını ölçüyor. Bir sembol çekilemezse
(ör. Binance'te o an mevcut değilse) fail-closed sessizce atlanıyor."""
from fastapi import APIRouter, Depends

from analytics.depeg_risk import compute_depeg_deviation
from exchange_gateway.binance.adapter import BinanceAdapter
from market_data.ingestion.ohlcv import from_binance_klines
from market_data.ingestion.yahoo_provider import YahooProvider
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/depeg-risk", tags=["depeg-risk"])

# XAUTUSDT/PAXGUSDT: 1 token = 1 troy ons altın, GC=F de $/ons — birim
# dönüşümü gerekmiyor, doğrudan karşılaştırılabilir.
_GOLD_PEGGED_SYMBOLS = ("XAUTUSDT", "PAXGUSDT")
_USD_PEGGED_SYMBOLS = ("USDCUSDT",)


async def _latest_binance_close(symbol: str) -> float | None:
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        raw = await adapter.fetch_ohlcv(symbol, "1m", limit=1)
    finally:
        await adapter.disconnect()
    bars = from_binance_klines(raw)
    return bars[-1].close if bars else None


@router.get("/")
async def depeg_risk(user: AuthContext = Depends(get_current_user)):
    results: dict[str, dict] = {}

    gold_bars = YahooProvider().get_ohlcv("GC=F", "1d", limit=1)
    gold_price = gold_bars[-1].close if gold_bars else None

    for sym in _GOLD_PEGGED_SYMBOLS:
        try:
            price = await _latest_binance_close(sym)
        except Exception:
            continue
        deviation = compute_depeg_deviation(price, gold_price)
        if deviation is not None:
            results[sym] = {"reference": "GC=F (spot gold)", **deviation}

    for sym in _USD_PEGGED_SYMBOLS:
        try:
            price = await _latest_binance_close(sym)
        except Exception:
            continue
        deviation = compute_depeg_deviation(price, 1.0)
        if deviation is not None:
            results[sym] = {"reference": "1.00 USD", **deviation}

    return {"pairs": results}
