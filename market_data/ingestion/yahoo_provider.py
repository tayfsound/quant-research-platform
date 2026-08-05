"""Faz 194: kripto-olmayan varlıklar (endeks/emtia/hisse) için gerçek OHLCV
kaynağı. Binance bunları sağlamıyor — Yahoo Finance (yfinance, key
gerektirmeyen ücretsiz seçenek) tek pratik alternatif."""
import logging

from market_data.ingestion.ohlcv import OHLCV

logger = logging.getLogger(__name__)

# 1m veri yfinance'te sadece son ~birkaç gün için tutuluyor — period'u
# limit'e göre değil, interval'in gerçekte desteklediği pencereye göre
# seçiyoruz (fazla istemek hata değil ama gereksiz/yavaş).
_INTERVAL_TO_PERIOD = {
    "1m": "5d",
    "5m": "1mo",
    "15m": "1mo",
    "1h": "3mo",
    "1d": "1y",
}


class YahooProvider:
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[OHLCV]:
        import yfinance as yf

        interval = timeframe if timeframe in _INTERVAL_TO_PERIOD else "1d"
        period = _INTERVAL_TO_PERIOD[interval]

        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
        except Exception as exc:
            logger.warning("Yahoo Finance fetch failed for %s: %s", symbol, exc)
            return []

        if df is None or df.empty:
            return []

        df = df.tail(limit)
        bars = []
        for ts, row in df.iterrows():
            bars.append(OHLCV(
                timestamp=ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            ))
        return bars
