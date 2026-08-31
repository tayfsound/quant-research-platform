"""Faz 392 — services/agent_combination_reliability_force_open.py.
services/short_exploration.py'nin kill switch / concurrent cap
testleriyle AYNI desen."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from database.session_factory import SessionFactory
from services.agent_combination_reliability_force_open import (
    EXPERIMENT_BUCKET,
    is_eligible,
)


def _insert_decision(symbol, status="closed", opened_at=None, closed_at=None, outcome=None):
    with SessionFactory.get_session() as session:
        session.execute(
            text(
                "INSERT INTO decisions (id, timestamp, symbol, direction, size, confidence, "
                "status, excluded_from_stats, leverage, experiment_bucket, opened_at, closed_at, outcome, "
                "agent_contributions) "
                "VALUES (:id, :ts, :symbol, 'LONG', 1.0, 0.9, :status, false, 1.0, "
                ":bucket, :opened_at, :closed_at, CAST(:outcome AS jsonb), '[]'::jsonb)"
            ),
            {
                "id": str(uuid4()), "ts": datetime.now(UTC), "symbol": symbol,
                "status": status, "bucket": EXPERIMENT_BUCKET, "opened_at": opened_at, "closed_at": closed_at,
                "outcome": __import__("json").dumps(outcome) if outcome else None,
            },
        )
        session.commit()


def _cleanup(symbols):
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = ANY(:syms)"), {"syms": symbols})
        session.commit()


def test_eligible_with_no_relevant_history():
    symbol = f"ACFO{uuid4().hex[:8]}"
    eligible, reason = is_eligible()
    assert eligible is True
    assert reason is None


def test_not_eligible_when_max_concurrent_reached():
    symbols = [f"ACFO{uuid4().hex[:8]}" for _ in range(5)]
    try:
        for s in symbols:
            _insert_decision(s, status="open", opened_at=datetime.now(UTC))
        eligible, reason = is_eligible()
        assert eligible is False
        assert reason == "max_concurrent_reached"
    finally:
        _cleanup(symbols)


def test_kill_switch_blocks_after_consecutive_losses():
    symbols = [f"ACFO{uuid4().hex[:8]}" for _ in range(3)]
    try:
        now = datetime.now(UTC)
        for i, s in enumerate(symbols):
            _insert_decision(
                s, status="closed", opened_at=now - timedelta(hours=i + 1),
                closed_at=now - timedelta(minutes=i + 1), outcome={"win": False},
            )
        eligible, reason = is_eligible()
        assert eligible is False
        assert reason == "force_open_kill_switch_active"
    finally:
        _cleanup(symbols)


def test_kill_switch_does_not_trigger_on_mixed_results():
    symbols = [f"ACFO{uuid4().hex[:8]}" for _ in range(3)]
    try:
        now = datetime.now(UTC)
        outcomes = [{"win": False}, {"win": True}, {"win": False}]
        for i, (s, outcome) in enumerate(zip(symbols, outcomes)):
            _insert_decision(
                s, status="closed", opened_at=now - timedelta(hours=i + 1),
                closed_at=now - timedelta(minutes=i + 1), outcome=outcome,
            )
        eligible, reason = is_eligible()
        assert eligible is True
        assert reason is None
    finally:
        _cleanup(symbols)
