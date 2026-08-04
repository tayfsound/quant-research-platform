"""Faz 164: Replay Determinism — gerçek DB persist → replay."""
from uuid import uuid4
from datetime import datetime, UTC
from contracts.decision_event import DecisionEvent
from services.decision_persistor import DecisionPersistor
from services.replay_engine import ReplayEngine
from database.session_factory import SessionFactory

def test_persist_then_replay():
    """Decision DB'ye persist et, sonra replay et — sonuç tutarlı."""
    event = DecisionEvent(
        id=uuid4(),
        symbol="BTCUSDT",
        proposed_direction="LONG",
        confidence=0.8,
        market_snapshot={"raw_snapshot": {"rsi": 30, "ema": 100}},
    )

    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        persistor.persist(event)

        # Replay
        engine = ReplayEngine(decision_repo=persistor)
        result = engine.replay_decision(str(event.id), deterministic=True)

        assert result["decision_id"] == str(event.id)
        assert result["symbol"] == "BTCUSDT"
        assert result["snapshot_restored"] is True
        assert result["deterministic"] is True
        # services/replay/ hash verification: replay must genuinely match the original
        assert result["verification"]["verified"] is True
        assert engine.verify_integrity(str(event.id)) is True

def test_replay_integrity_hash():
    """verify_integrity: decision hash doğrula."""
    event = DecisionEvent(
        id=uuid4(),
        symbol="ETHUSDT",
        proposed_direction="SHORT",
        confidence=0.6,
    )

    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        persistor.persist(event)

        engine = ReplayEngine(decision_repo=persistor)
        # İlk replay
        r1 = engine.replay_decision(str(event.id), deterministic=True)
        # İkinci replay (aynı seed = aynı sonuç)
        r2 = engine.replay_decision(str(event.id), deterministic=True)
        
        assert r1["direction"] == r2["direction"]
        assert r1["confidence"] == r2["confidence"]
