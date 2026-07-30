"""Ortak OHLCV modeli."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

def from_binance_kline(row: dict[str, Any] | list[Any]) -> OHLCV:
    if isinstance(row, list):
        ts = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
        return OHLCV(timestamp=ts, open=float(row[1]), high=float(row[2]),
                     low=float(row[3]), close=float(row[4]), volume=float(row[5]))
    ts_raw = row.get("time") or row.get("timestamp")
    if isinstance(ts_raw, (int, float)):
        ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)
    else:
        ts = ts_raw if isinstance(ts_raw, datetime) else datetime.now(timezone.utc)
    return OHLCV(timestamp=ts, open=float(row["open"]), high=float(row["high"]),
                 low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"]))

def from_binance_klines(rows: list[Any]) -> list[OHLCV]:
    return [from_binance_kline(r) for r in rows]
