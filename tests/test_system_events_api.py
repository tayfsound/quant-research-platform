"""GET /api/v1/system-events/ — Faz 269 (Cognitive Core 2.0 / M1)."""
from unittest.mock import patch
from uuid import uuid4


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_system_events_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/system-events/")
        assert response.status_code in (401, 403)


def test_system_events_returns_real_recorded_events():
    from database.repositories.event_log_repository import EventLogRepository
    from database.session_factory import SessionFactory
    from tests.auth_helpers import make_authed_headers

    event_type = f"test_api_event_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        EventLogRepository(session).record(event_type, payload={"n": 1})

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get(
            f"/api/v1/system-events/?event_type={event_type}", headers=make_authed_headers()
        )
        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) == 1
        assert events[0]["payload"]["n"] == 1
