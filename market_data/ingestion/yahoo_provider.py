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

# Faz 214: yfinance'in gerçek intraday aralıkları 1h'de kesiliyor — "4h"
# diye bir interval yok. Önceden bu durumda sessizce "1d"ye düşülüyordu
# (kullanıcı 4h istese bile günlük bara geçiliyordu, fark edilmeden).
# Dürüst çözüm: 1h barları çekip her 4'ünü gerçek OHLCV kurallarıyla
# (open=ilk, high=max, low=min, close=son, volume=toplam) 4h'e
# yeniden örneklemek — uydurma veri değil, standart downsampling.
_RESAMPLE_FROM = {"4h": ("1h", 4)}


class YahooProvider:
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[OHLCV]:
        import yfinance as yf

        if timeframe in _RESAMPLE_FROM:
            base_interval, factor = _RESAMPLE_FROM[timeframe]
            base_bars = self._fetch(yf, symbol, base_interval, limit * factor + factor)
            return self._resample(base_bars, factor)[-limit:]

        return self._fetch(yf, symbol, timeframe, limit)

    def _fetch(self, yf, symbol: str, timeframe: str, limit: int) -> list[OHLCV]:
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

    @staticmethod
    def _resample(bars: list[OHLCV], factor: int) -> list[OHLCV]:
        resampled = []
        for i in range(0, len(bars) - factor + 1, factor):
            chunk = bars[i:i + factor]
            resampled.append(OHLCV(
                timestamp=chunk[0].timestamp,
                open=chunk[0].open,
                high=max(b.high for b in chunk),
                low=min(b.low for b in chunk),
                close=chunk[-1].close,
                volume=sum(b.volume for b in chunk),
            ))
        return resampled
