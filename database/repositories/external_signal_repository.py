"""External Signal repository — TradingView webhook alarm sinyalleri."""
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text


class ExternalSignalRepository:
    def __init__(self, session):
        self.session = session

    def save(self, *, source: str, symbol: str, signal: str | None, payload: dict) -> UUID:
        signal_id = uuid4()
        self.session.execute(
            text("""
                INSERT INTO external_signals (id, time, source, symbol, signal, payload)
                VALUES (:id, :time, :source, :symbol, :signal, CAST(:payload AS jsonb))
            """),
            {
                "id": str(signal_id),
                "time": datetime.now(UTC),
                "source": source,
                "symbol": symbol,
                "signal": signal,
                "payload": json.dumps(payload, default=str),
            },
        )
        self.session.commit()
        return signal_id

    def get_recent(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        if symbol:
            rows = self.session.execute(
                text("""
                    SELECT * FROM external_signals WHERE symbol = :symbol
                    ORDER BY time DESC LIMIT :limit
                """),
                {"symbol": symbol, "limit": limit},
            ).mappings().all()
        else:
            rows = self.session.execute(
                text("SELECT * FROM external_signals ORDER BY time DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_latest_for_symbol(self, symbol: str) -> dict | None:
        row = self.session.execute(
            text("""
                SELECT * FROM external_signals WHERE symbol = :symbol
                ORDER BY time DESC LIMIT 1
            """),
            {"symbol": symbol},
        ).mappings().first()
        return dict(row) if row else None
