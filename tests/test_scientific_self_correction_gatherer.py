"""Faz 356 — services/scientific_self_correction_gatherer.py gerçek veri
entegrasyon testleri (analytics/scientific_self_correction.py'nin kendi
saf-fonksiyon testleri tests/test_scientific_self_correction.py'de zaten var)."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.scientific_self_correction_gatherer import gather_scientific_self_correction

_SYMBOL = "SSCTESTUSDT"


def _persist_closed_trade(direction: str, win: bool, closed_at: datetime, experiment_bucket: str | None = None) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(),
            symbol=_SYMBOL,
            proposed_direction=direction,
            final_action=direction,
            final_size=0.1,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10),
            agent_opinions=[],
            market_snapshot={"features": {}},
            experiment_bucket=experiment_bucket,
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id),
            exit_price=101.0 if win else 99.0,
            pnl=1.0 if win else -1.0,
            closed_at=closed_at,
            outcome={"win": win},
        )


def _cleanup() -> None:
    with SessionFactory.get_session() as session:
        from sqlalchemy import text
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": _SYMBOL})
        session.commit()


def test_gather_scientific_self_correction_flags_real_degradation():
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    try:
        for _ in range(23):
            _persist_closed_trade("LONG", True, old)
        for _ in range(2):
            _persist_closed_trade("LONG", False, old)
        for _ in range(5):
            _persist_closed_trade("LONG", True, now - timedelta(hours=1))
        for _ in range(20):
            _persist_closed_trade("LONG", False, now - timedelta(hours=1))

        result = gather_scientific_self_correction(recent_days=7)
        long_segment = result["segments"]["direction=LONG"]
        assert long_segment["original_win_rate"] > long_segment["recent_win_rate"]
        assert long_segment["significant_change"] is True
        assert long_segment["hypothesis_still_valid"] is False
    finally:
        _cleanup()


def test_gather_scientific_self_correction_excludes_mechanical_strategies():
    """pump_fade/basis_arb kendi risk yönetimlerine sahip mekanik
    stratejiler — council'in isabetini yansıtmadıkları için hiçbir
    segmente karışmamalı (kill switch/concept drift'le AYNI ilke)."""
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    try:
        for _ in range(25):
            _persist_closed_trade("SHORT", False, old, experiment_bucket="pump_fade_v1")
        for _ in range(25):
            _persist_closed_trade("SHORT", False, now - timedelta(hours=1), experiment_bucket="pump_fade_v1")

        result = gather_scientific_self_correction(recent_days=7)
        assert "experiment_bucket=pump_fade_v1" not in result["segments"]
        assert "direction=SHORT" not in result["segments"]
    finally:
        _cleanup()


def test_gather_scientific_self_correction_fail_closed_below_min_sample():
    now = datetime.now(UTC)

    try:
        _persist_closed_trade("LONG", True, now - timedelta(hours=1))

        result = gather_scientific_self_correction(recent_days=7)
        assert result["segments"] == {}
    finally:
        _cleanup()
