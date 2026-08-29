"""Faz 372 — SHORT Exploration deneyi testleri.

bkz. services/short_exploration.py, services/decision_fusion.py (çağrı
noktası). Amaç: normal SHORT/EV davranışını hiç değiştirmeden, sıkı
hard-cap'li/izole bir keşif kovası."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from database.session_factory import SessionFactory
from services.short_exploration import (
    EXPERIMENT_BUCKET,
    is_eligible,
)


def _insert_decision(
    symbol, direction="SHORT", confidence=0.5, status="no_trade",
    experiment_bucket=None, opened_at=None, closed_at=None, outcome=None,
    timestamp=None,
):
    with SessionFactory.get_session() as session:
        session.execute(
            text(
                "INSERT INTO decisions (id, timestamp, symbol, direction, size, confidence, "
                "status, excluded_from_stats, leverage, experiment_bucket, opened_at, closed_at, outcome, "
                "agent_contributions) "
                "VALUES (:id, :ts, :symbol, :direction, 1.0, :confidence, :status, false, 1.0, "
                ":bucket, :opened_at, :closed_at, CAST(:outcome AS jsonb), '[]'::jsonb)"
            ),
            {
                "id": str(uuid4()), "ts": timestamp or datetime.now(UTC), "symbol": symbol,
                "direction": direction, "confidence": confidence, "status": status,
                "bucket": experiment_bucket, "opened_at": opened_at, "closed_at": closed_at,
                "outcome": __import__("json").dumps(outcome) if outcome else None,
            },
        )
        session.commit()


def _cleanup(symbols):
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = ANY(:syms)"), {"syms": symbols})
        session.commit()


def test_not_eligible_when_insufficient_recent_short_samples(monkeypatch):
    """Paylaşılan test DB'sinde zaten yüzlerce gerçek SHORT kaydı olabilir
    — gerçek DB durumundan bağımsız, deterministik test için
    _recent_short_confidences doğrudan monkeypatch'lendi."""
    monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.9] * 5)
    eligible, reason = is_eligible("SOLUSDT", confidence=0.95)
    assert eligible is False
    assert reason == "insufficient_recent_short_samples_for_percentile"


def test_not_eligible_when_confidence_below_dynamic_percentile(monkeypatch):
    # %20'si yüksek (0.9), %80'i düşük (0.3) — P85 bu dağılımda 0.9'a düşer.
    monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.3] * 80 + [0.9] * 20)
    monkeypatch.setattr("services.short_exploration._kill_switch_triggered", lambda: False)
    eligible, reason = is_eligible("SOLUSDT", confidence=0.4)
    assert eligible is False
    assert reason == "below_dynamic_confidence_percentile"


def test_eligible_when_confidence_at_high_percentile_and_no_caps_hit(monkeypatch):
    symbol = f"SHEXP{uuid4().hex[:8]}"
    try:
        monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.3] * 50 + [0.5] * 30)
        monkeypatch.setattr("services.short_exploration._kill_switch_triggered", lambda: False)
        eligible, reason = is_eligible(symbol, confidence=0.9)
        assert eligible is True
        assert reason is None
    finally:
        _cleanup([symbol])


def test_not_eligible_when_max_concurrent_reached(monkeypatch):
    symbol = f"SHEXP{uuid4().hex[:8]}"
    other_symbol = f"SHEXP{uuid4().hex[:8]}"
    try:
        monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.3] * 50)
        monkeypatch.setattr("services.short_exploration._kill_switch_triggered", lambda: False)
        # MAX_CONCURRENT=2 -> 2 açık pozisyon zaten var.
        _insert_decision(symbol, status="open", experiment_bucket=EXPERIMENT_BUCKET, opened_at=datetime.now(UTC))
        _insert_decision(other_symbol, status="open", experiment_bucket=EXPERIMENT_BUCKET, opened_at=datetime.now(UTC))

        eligible, reason = is_eligible(f"SHEXP{uuid4().hex[:8]}", confidence=0.9)
        assert eligible is False
        assert reason == "max_concurrent_reached"
    finally:
        _cleanup([symbol, other_symbol])


def test_not_eligible_when_symbol_cooldown_active(monkeypatch):
    symbol = f"SHEXP{uuid4().hex[:8]}"
    try:
        monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.3] * 50)
        monkeypatch.setattr("services.short_exploration._kill_switch_triggered", lambda: False)
        _insert_decision(
            symbol, status="closed", experiment_bucket=EXPERIMENT_BUCKET,
            opened_at=datetime.now(UTC) - timedelta(hours=6), closed_at=datetime.now(UTC),
            outcome={"win": True},
        )

        eligible, reason = is_eligible(symbol, confidence=0.9)
        assert eligible is False
        assert reason == "symbol_cooldown_active"
    finally:
        _cleanup([symbol])


def test_eligible_again_after_symbol_cooldown_expires(monkeypatch):
    symbol = f"SHEXP{uuid4().hex[:8]}"
    try:
        monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.3] * 50)
        monkeypatch.setattr("services.short_exploration._kill_switch_triggered", lambda: False)
        _insert_decision(
            symbol, status="closed", experiment_bucket=EXPERIMENT_BUCKET,
            opened_at=datetime.now(UTC) - timedelta(days=10), closed_at=datetime.now(UTC) - timedelta(days=9),
            outcome={"win": True},
        )

        eligible, reason = is_eligible(symbol, confidence=0.9)
        assert eligible is True
    finally:
        _cleanup([symbol])


def test_kill_switch_blocks_after_consecutive_losses(monkeypatch):
    monkeypatch.setattr("services.short_exploration._recent_short_confidences", lambda limit=200: [0.3] * 50)
    symbol = f"SHEXP{uuid4().hex[:8]}"
    try:
        now = datetime.now(UTC)
        for i in range(3):
            _insert_decision(
                f"{symbol}{i}", status="closed", experiment_bucket=EXPERIMENT_BUCKET,
                opened_at=now - timedelta(hours=i + 1), closed_at=now - timedelta(minutes=i + 1),
                outcome={"win": False},
            )

        eligible, reason = is_eligible(symbol, confidence=0.99)
        assert eligible is False
        assert reason == "exploration_kill_switch_active"
    finally:
        _cleanup([f"{symbol}0", f"{symbol}1", f"{symbol}2", symbol])
