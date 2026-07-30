"""Teknik göstergeler."""
from typing import List, Dict
from market_data.ingestion.mock_adapter import OHLCV

def rsi(data: List[OHLCV], period: int = 14) -> float:
    if len(data) < period + 1:
        return 50.0
    closes = [d.close for d in data]
    gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def ema(data: List[OHLCV], period: int = 20) -> float:
    if len(data) < period:
        return data[-1].close if data else 0.0
    closes = [d.close for d in data]
    multiplier = 2.0 / (period + 1)
    ema_val = sum(closes[:period]) / period
    for price in closes[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val

def macd(data: List[OHLCV]) -> Dict[str, float]:
    ema12 = ema(data, 12)
    ema26 = ema(data, 26)
    macd_line = ema12 - ema26
    return {"macd": macd_line, "signal": macd_line * 0.9}
