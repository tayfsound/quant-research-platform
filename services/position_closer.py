"""Faz 187: gerçek pozisyon kapanışı.

services/forward_outcome.py'nin "backtest tarzı" hesaplamasından farkı:
orada entry VE exit aynı anda, aynı zaten-var-olan geçmiş OHLCV penceresinden
okunuyordu (yani hiçbir zaman gerçekten zaman geçmesini beklemiyordu). Burada
entry_price pozisyon gerçekten açıldığı anda sabitlenmiş durumda, exit_price
ise gerçekten şimdi (kapanış anında) çekilen güncel fiyat — aradan gerçekten
en az `hold_seconds` kadar gerçek zaman geçmiş olmalı.
"""
from datetime import UTC, datetime

from database.repositories.decision_persistor import DecisionPersistor
from market_data.ingestion.data_provider import OHLCVProvider
from simulator.fee_engine import FeeEngine


class PositionCloser:
    def __init__(
        self,
        data_provider: OHLCVProvider,
        hold_seconds: int = 600,
        fee_engine: FeeEngine | None = None,
    ):
        self.data_provider = data_provider
        self.hold_seconds = hold_seconds
        self.fee_engine = fee_engine or FeeEngine()

    def _age_seconds(self, opened_at: datetime, now: datetime) -> float:
        # Bilinen borç (CURRENT_STATE.md'de dokümante): DB'de naive/aware
        # datetime karışık olabilir. Burada ikisini de kabul ediyoruz.
        if opened_at.tzinfo is None:
            return (now.replace(tzinfo=None) - opened_at).total_seconds()
        return (now - opened_at).total_seconds()

    def close_due_positions(self, decision_repo: DecisionPersistor, timeframe: str = "1m") -> list[dict]:
        """Yeterince zaman geçmiş (hold_seconds) açık pozisyonları gerçek
        güncel fiyatla kapatır. Kapatılanların özetini döndürür."""
        now = datetime.now(UTC)
        closed = []

        for pos in decision_repo.list_open_positions():
            opened_at = pos.get("opened_at")
            entry_price = pos.get("entry_price")
            if opened_at is None or entry_price is None:
                continue
            if self._age_seconds(opened_at, now) < self.hold_seconds:
                continue

            symbol = pos["symbol"]
            data = self.data_provider.get_ohlcv(symbol, timeframe, limit=1)
            if not data:
                continue
            exit_price = data[-1].close
            quantity = pos.get("quantity") or 0.0
            direction = (pos.get("direction") or "").upper()

            if direction == "LONG":
                gross_pnl = (exit_price - entry_price) * quantity
            elif direction == "SHORT":
                gross_pnl = (entry_price - exit_price) * quantity
            else:
                gross_pnl = 0.0

            fee = self.fee_engine.calculate(entry_price * quantity) + self.fee_engine.calculate(exit_price * quantity)
            pnl = gross_pnl - fee

            decision_repo.close_position(
                decision_id=str(pos["id"]),
                exit_price=exit_price,
                pnl=pnl,
                closed_at=now,
                outcome={
                    "pnl": pnl,
                    "gross_pnl": gross_pnl,
                    "fee": fee,
                    "win": pnl > 0,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "hold_seconds": self._age_seconds(opened_at, now),
                },
            )
            closed.append({"decision_id": str(pos["id"]), "symbol": symbol, "pnl": pnl, "win": pnl > 0})

        return closed
