"""POST /api/v1/replay/decision/{id} — real DB record -> real API replay -> verified."""
from unittest.mock import patch
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


def test_replay_decision_endpoint_verifies_real_recorded_decision():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app

            event = DecisionEvent(
                id=uuid4(),
                symbol="BTCUSDT",
                proposed_direction="LONG",
                confidence=0.8,
                market_snapshot={"raw_snapshot": {"rsi": 30, "ema": 100}},
            )
            with SessionFactory.get_session() as session:
                DecisionPersistor(session).persist(event)

            from contracts.auth import Role
            from tests.auth_helpers import make_authed_headers

            client = TestClient(app)
            response = client.post(
                f"/api/v1/replay/decision/{event.id}",
                headers=make_authed_headers(Role.VIEWER),
            )

            assert response.status_code == 200
            body = response.json()
            assert body["decision_id"] == str(event.id)
            # database/repositories/decision_persistor.py now writes market_snapshot
            # into agent_contributions, so replay must actually restore it.
            assert body["snapshot_restored"] is True
            assert body["verification"]["verified"] is True
