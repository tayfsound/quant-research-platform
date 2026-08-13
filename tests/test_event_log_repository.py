"""Faz 269 (Cognitive Core 2.0 / M1): system_events — Veri ve olay altyapısı."""
from uuid import uuid4

from database.repositories.event_log_repository import EventLogRepository
from database.session_factory import SessionFactory


def test_record_and_list_a_real_event():
    with SessionFactory.get_session() as session:
        repo = EventLogRepository(session)
        event_type = f"test_event_{uuid4().hex[:8]}"
        repo.record(event_type, entity_type="risk", payload={"consecutive_losses": 12})

        events = repo.list_events(event_type=event_type, limit=10)
        assert len(events) == 1
        assert events[0]["entity_type"] == "risk"
        assert events[0]["payload"]["consecutive_losses"] == 12


def test_record_defaults_entity_fields_to_none():
    with SessionFactory.get_session() as session:
        repo = EventLogRepository(session)
        event_type = f"test_event_{uuid4().hex[:8]}"
        repo.record(event_type)

        events = repo.list_events(event_type=event_type, limit=10)
        assert events[0]["entity_type"] is None
        assert events[0]["entity_id"] is None
        assert events[0]["payload"] == {}


def test_list_events_filters_by_event_type():
    with SessionFactory.get_session() as session:
        repo = EventLogRepository(session)
        type_a = f"test_event_a_{uuid4().hex[:8]}"
        type_b = f"test_event_b_{uuid4().hex[:8]}"
        repo.record(type_a)
        repo.record(type_b)

        events_a = repo.list_events(event_type=type_a, limit=10)
        assert len(events_a) == 1
        assert events_a[0]["event_type"] == type_a


def test_list_events_orders_most_recent_first():
    with SessionFactory.get_session() as session:
        repo = EventLogRepository(session)
        event_type = f"test_event_order_{uuid4().hex[:8]}"
        repo.record(event_type, payload={"seq": 1})
        repo.record(event_type, payload={"seq": 2})
        repo.record(event_type, payload={"seq": 3})

        events = repo.list_events(event_type=event_type, limit=10)
        assert [e["payload"]["seq"] for e in events] == [3, 2, 1]


def test_record_never_raises_even_if_it_cannot_persist(monkeypatch):
    """RiskEngine._trip_kill_switch()'in kendi try/except'iyle AYNI
    felsefe: bir olayı kaydedememek çağıran tarafın GERÇEK işini
    engellememeli. session.add'i (SessionFactory.get_session()'ın çıkışta
    yaptığı İKİNCİ commit'le çakışmadan) hatalandırıyoruz — record()'un
    kendi try/except'i bunu yutmalı, hiçbir eklenmemiş satır olmadığı için
    dış context manager'ın kendi commit'i de sorunsuz geçer."""
    with SessionFactory.get_session() as session:
        repo = EventLogRepository(session)

        def boom(*args, **kwargs):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(session, "add", boom)
        repo.record("should_not_raise")  # exception fırlatmamalı
