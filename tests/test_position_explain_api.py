"""Faz 268-sonrası — kullanıcı isteği: Transaction sayfasında "hangi
ajandan ne karar geldiğini gösteren açıklayan bir fonksiyon." decisions.
agent_contributions'ta zaten kayıtlı olan ham veriyi (her ajanın gerçek
oyu + council belief + debate/itiraz sonucu + InnerCritic + DecisionFusion
gerekçesi) ayrıştırıp döndüren GET /positions/{id}/explain endpoint'i."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def _persist_decision_with_full_agent_contributions() -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol="BTCUSDT",
        proposed_direction="LONG", final_action="LONG", final_size=0.2, confidence=0.72,
        status="open", entry_price=100.0, quantity=0.2, opened_at=now,
        stop_loss_price=95.0, take_profit_price=105.0,
        agent_opinions=[
            {
                "domain": "technical", "direction": "LONG", "confidence": 0.75,
                "effective_influence": 0.6, "performance_weight": 1.0,
                "evidence": ["Bullish trend"], "caveats": [],
            },
            {
                "domain": "macro", "direction": "WAIT", "confidence": 0.4,
                "effective_influence": 0.2, "performance_weight": 1.0,
                "evidence": [], "caveats": ["Mixed macro signals"],
            },
            {"type": "weight_snapshot", "data": {"id": str(uuid4())}},
            {"type": "council_belief", "data": {"direction": "LONG", "strength": 0.7}},
            {"type": "debate_result", "data": {"reasoning": "Final: LONG (conf 0.7)"}},
            {"type": "inner_critic", "data": {"risk_flags": ["high_volatility"], "objections": []}},
            {"type": "decision_fusion", "data": {"adjustment": "R/R too low, size halved", "rr": 0.4}},
        ],
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def test_explain_requires_auth():
    client = _client()
    response = client.get(f"/api/v1/positions/{uuid4()}/explain")
    assert response.status_code in (401, 403)


def test_explain_returns_404_for_unknown_decision():
    client = _client()
    response = client.get(f"/api/v1/positions/{uuid4()}/explain", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 404


def test_explain_separates_agent_votes_from_special_entries():
    event = _persist_decision_with_full_agent_contributions()
    client = _client()
    response = client.get(f"/api/v1/positions/{event.id}/explain", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "BTCUSDT"
    assert body["final_direction"] == "LONG"

    domains = {v["domain"] for v in body["agent_votes"]}
    assert domains == {"technical", "macro"}
    technical_vote = next(v for v in body["agent_votes"] if v["domain"] == "technical")
    assert technical_vote["direction"] == "LONG"
    assert technical_vote["confidence"] == 0.75

    assert body["council_belief"] == {"direction": "LONG", "strength": 0.7}
    assert body["debate_result"] == {"reasoning": "Final: LONG (conf 0.7)"}
    assert body["inner_critic"] == {"risk_flags": ["high_volatility"], "objections": []}
    assert body["decision_fusion"] == [{"adjustment": "R/R too low, size halved", "rr": 0.4}]
    assert body["weight_snapshot_id"] is not None


def test_explain_handles_a_decision_with_no_agent_contributions_gracefully():
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol="ETHUSDT",
        proposed_direction="WAIT", final_action="WAIT", final_size=0.0, confidence=0.0,
        status="no_trade",
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    client = _client()
    response = client.get(f"/api/v1/positions/{event.id}/explain", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert body["agent_votes"] == []
    assert body["council_belief"] is None
    assert body["decision_fusion"] == []
