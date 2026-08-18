"""Faz 269-sonrası — kullanıcı isteği "Event sourcing / event store": tablo
ve EventLogRepository zaten vardı (Faz 269), sadece kill_switch_tripped
yazıyordu. Bu, todo'daki diğer üç olayı (PositionOpened, PositionClosed,
WeightApproved) gerçek yazma noktalarına (DecisionPersistor.persist/
close_position, WeightApprovalRepository.approve) ekliyor — RiskEngine'in
kendi olayını nasıl yazdığıyla AYNI desen."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from contracts.weight_approval import WeightApproval
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.event_log_repository import EventLogRepository
from database.repositories.weight_approval_repository import WeightApprovalRepository
from database.session_factory import SessionFactory


def test_persist_records_position_opened_event_for_a_real_open_position():
    symbol = f"EVTOPEN{uuid4().hex[:6]}USDT"
    event_id = uuid4()

    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(
            DecisionEvent(
                id=event_id, symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, confidence=0.7, status="open", entry_price=100.0, quantity=1.0,
            )
        )

        events = EventLogRepository(session).list_events(event_type="position_opened", limit=200)

    matching = [e for e in events if e["entity_id"] == str(event_id)]
    assert len(matching) == 1
    assert matching[0]["payload"]["symbol"] == symbol
    assert matching[0]["payload"]["direction"] == "LONG"


def test_persist_does_not_record_position_opened_for_a_no_trade_decision():
    symbol = f"EVTNOTRADE{uuid4().hex[:6]}USDT"
    event_id = uuid4()

    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(
            DecisionEvent(
                id=event_id, symbol=symbol, proposed_direction="WAIT", final_action="WAIT",
                final_size=0.0, confidence=0.5, status="no_trade",
            )
        )

        events = EventLogRepository(session).list_events(event_type="position_opened", limit=200)

    assert all(e["entity_id"] != str(event_id) for e in events)


def test_close_position_records_position_closed_event_for_a_real_close():
    symbol = f"EVTCLOSE{uuid4().hex[:6]}USDT"
    event_id = uuid4()
    now = datetime.now(UTC)

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        repo.persist(
            DecisionEvent(
                id=event_id, symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, confidence=0.7, status="open", entry_price=100.0, quantity=1.0,
            )
        )
        repo.close_position(decision_id=str(event_id), exit_price=105.0, pnl=50.0, closed_at=now)

        events = EventLogRepository(session).list_events(event_type="position_closed", limit=200)

    matching = [e for e in events if e["entity_id"] == str(event_id)]
    assert len(matching) == 1
    assert matching[0]["payload"]["exit_price"] == 105.0
    assert matching[0]["payload"]["pnl"] == 50.0


def test_approve_records_weight_approved_event_for_a_real_approval():
    approval_id = uuid4()

    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        repo.save(WeightApproval(
            id=approval_id, proposed_weights={"technical": 1.2}, previous_weights={"technical": 1.0},
            max_delta=0.1, status="pending", timestamp=datetime.now(),
        ))
        repo.approve(str(approval_id), approved_by="test_operator")

        events = EventLogRepository(session).list_events(event_type="weight_approved", limit=200)

    matching = [e for e in events if e["entity_id"] == str(approval_id)]
    assert len(matching) == 1
    assert matching[0]["payload"]["approved_by"] == "test_operator"
