"""Teknik gösterge hesaplamaları."""
from typing import Any

import numpy as np


def ema(prices: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(alpha * p + (1 - alpha) * result[-1])
    return result

def sma(prices: list[float], period: int) -> list[float]:
    return list(np.convolve(prices, np.ones(period) / period, mode="valid"))

def rsi(prices: list[float], period: int = 14) -> float:
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def macd(prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Any]:
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return {"macd": macd_line[-1], "signal": signal_line[-1], "histogram": histogram[-1]}

def vwap(prices: list[float], volumes: list[float]) -> float:
    total = sum(p * v for p, v in zip(prices, volumes))
    return total / sum(volumes) if sum(volumes) > 0 else 0.0

def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    tr = [max(h - l, abs(h - closes[i - 1]), abs(l - closes[i - 1])) if i > 0 else h - l
          for i, (h, l) in enumerate(zip(highs, lows))]
    return float(np.mean(tr[-period:]))
