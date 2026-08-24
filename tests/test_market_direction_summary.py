"""Faz 362-devam — backlog madde 21: "AI şu an piyasa yönünü nasıl görüyor"
bilgi kartı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


def _cleanup(symbols: list[str]) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = ANY(:symbols)"), {"symbols": symbols})
        session.commit()


def _persist(symbol: str, direction: str, confidence: float, when: datetime) -> None:
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction=direction, final_action=direction,
            confidence=confidence, status="no_trade", timestamp=when,
        ))


def test_latest_direction_confidence_returns_only_the_most_recent_per_symbol():
    long_symbol = f"MKTDIR{uuid4().hex[:8]}USDT"
    short_symbol = f"MKTDIR{uuid4().hex[:8]}USDT"
    now = datetime.now(UTC)
    try:
        # long_symbol: eski SHORT, yeni LONG -- sadece yeni olan donmeli
        _persist(long_symbol, "SHORT", 0.9, now - timedelta(minutes=5))
        _persist(long_symbol, "LONG", 0.7, now)
        _persist(short_symbol, "SHORT", 0.6, now)

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).latest_direction_confidence_by_symbol(
                since=now - timedelta(minutes=10)
            )
        by_symbol = {r["symbol"]: r for r in rows}

        assert by_symbol[long_symbol]["direction"] == "LONG"
        assert by_symbol[long_symbol]["confidence"] == 0.7
        assert by_symbol[short_symbol]["direction"] == "SHORT"
    finally:
        _cleanup([long_symbol, short_symbol])


def test_latest_direction_confidence_excludes_stale_symbols_via_since():
    symbol = f"MKTDIR{uuid4().hex[:8]}USDT"
    now = datetime.now(UTC)
    try:
        _persist(symbol, "LONG", 0.9, now - timedelta(days=2))

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).latest_direction_confidence_by_symbol(
                since=now - timedelta(hours=24)
            )
        assert symbol not in {r["symbol"] for r in rows}
    finally:
        _cleanup([symbol])
