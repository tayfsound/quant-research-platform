"""Ortak OHLCV modeli."""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    # Faz 461 — Binance klines cevabinda ZATEN gelen order-flow alanlari.
    # Varsayilan None: bu alanlari vermeyen kaynaklar (MockProvider,
    # Yahoo Finance, eski cagri yollari) hic degismeden calismaya devam
    # eder ve UYDURMA bir deger uretilmez (fail-closed).
    quote_volume: float | None = None
    trades: int | None = None
    taker_buy_base: float | None = None
    taker_buy_quote: float | None = None

def from_binance_kline(row: dict[str, Any] | list[Any]) -> OHLCV:
    if isinstance(row, list):
        # Binance'in HAM 12 alanli kline dizisi -- d[7]/d[8]/d[9]/d[10]
        # Faz 461'e kadar burada da atiliyordu.
        ts = datetime.fromtimestamp(row[0] / 1000, tz=UTC)

        def _f(idx: int) -> float | None:
            try:
                return float(row[idx])
            except (IndexError, TypeError, ValueError):
                return None

        def _i(idx: int) -> int | None:
            try:
                return int(row[idx])
            except (IndexError, TypeError, ValueError):
                return None

        return OHLCV(timestamp=ts, open=float(row[1]), high=float(row[2]),
                     low=float(row[3]), close=float(row[4]), volume=float(row[5]),
                     quote_volume=_f(7), trades=_i(8),
                     taker_buy_base=_f(9), taker_buy_quote=_f(10))
    ts_raw = row.get("time") or row.get("timestamp")
    if isinstance(ts_raw, (int, float)):
        ts = datetime.fromtimestamp(ts_raw / 1000, tz=UTC)
    else:
        ts = ts_raw if isinstance(ts_raw, datetime) else datetime.now(UTC)
    return OHLCV(timestamp=ts, open=float(row["open"]), high=float(row["high"]),
                 low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"]),
                 quote_volume=row.get("quote_volume"), trades=row.get("trades"),
                 taker_buy_base=row.get("taker_buy_base"),
                 taker_buy_quote=row.get("taker_buy_quote"))

def from_binance_klines(rows: list[Any]) -> list[OHLCV]:
    return [from_binance_kline(r) for r in rows]
