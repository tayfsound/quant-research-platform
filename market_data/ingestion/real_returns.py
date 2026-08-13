"""Faz 270-sonrası: birden fazla analytics API'sinin (correlation-breakdown,
liquidity-var) AYNI ihtiyacı — bir sembolün GERÇEK geçmiş kapanış
fiyatlarından dönemsel getiri serisi. Binance dışı semboller (GC=F, SI=F
gibi yfinance kaynaklılar) burada desteklenmiyor — çağıran taraf
exception'ı fail-closed (sessizce atlayarak) ele almalı."""
from exchange_gateway.binance.adapter import BinanceAdapter
from market_data.ingestion.ohlcv import from_binance_klines


async def fetch_symbol_returns(symbol: str, timeframe: str, limit: int) -> list[float]:
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
