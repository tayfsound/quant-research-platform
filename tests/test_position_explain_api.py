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
            {
                "type": "portfolio_confidence_discount",
                "data": {
                    "reason": "same_direction_correlation",
                    "confidence_before": 0.9,
                    "confidence_after": 0.72,
                    "multiplier": 0.8,
                },
            },
            {
                "type": "cross_asset_context",
                "data": {"cause": "BTCUSDT", "best_lag": 3, "best_p_value": 0.012, "sample_size": 180},
            },
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

    # Kullanıcı bulgusu: "%74 güvenli bir ajan varken nihai karar neden
    # %28 çıktı?" — bu indirim artık explain sayfasında açıkça görünüyor.
    assert body["portfolio_confidence_discounts"] == [{
        "reason": "same_direction_correlation",
        "confidence_before": 0.9,
        "confidence_after": 0.72,
        "multiplier": 0.8,
    }]

    # FIL Faz C — kullanıcı isteği: Causal Inference bağlamı (Granger
    # causality) da açıklama ekranında görünmeli, visibility-only.
    assert body["cross_asset_context"] == [
        {"cause": "BTCUSDT", "best_lag": 3, "best_p_value": 0.012, "sample_size": 180},
    ]


def test_explain_summarizes_net_evidence_by_direction_and_carries_weight_adjustments():
    """Faz 376 — kullanıcı bulgusu (canlı bir PYPLUSDT LONG %65.7 örneği):
    "Sistem şu anda sadece 'kanıta göre karar vermiyor'; kanıtın kendisini
    çok katmanlı cezalarla yeniden şekillendiriyor... hangi ajan/feature
    sadece bastırılmış durumda?" — net_evidence_by_direction bunu tek
    bakışta gösteriyor: yönü aynı olan ajanları "aktif" (hiç ayarlama
    görmemiş) ve "bastırılmış" (en az bir weight_adjustments girdisi
    olan) diye ayırıyor."""
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol="PYPLUSDT",
        proposed_direction="LONG", final_action="LONG", final_size=0.2, confidence=0.657,
        status="open", entry_price=100.0, quantity=0.2, opened_at=now,
        stop_loss_price=95.0, take_profit_price=105.0,
        agent_opinions=[
            {
                "domain": "technical", "direction": "LONG", "confidence": 0.696,
                "raw_confidence": 0.218, "source_reliability": 0.524, "intrinsic_trust": 0.739,
                "effective_influence": 0.028, "performance_weight": 0.055,
                "weight_adjustments": [
                    {"step": "benching_floor", "before": 1.0, "after": 0.1, "detail": "..."},
                    {"step": "unanswered_debate_challenge", "before": 0.1, "after": 0.07, "multiplier": 0.7},
                ],
                "evidence": ["Bullish trend"], "caveats": ["Devre dışı (benched)"],
            },
            {
                "domain": "order_flow", "direction": "LONG", "confidence": 0.55,
                "raw_confidence": 0.429, "source_reliability": 0.529, "intrinsic_trust": 0.693,
                "effective_influence": 0.267, "performance_weight": 0.70,
                "weight_adjustments": [],
                "evidence": ["Aggressive buying"], "caveats": [],
            },
        ],
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    client = _client()
    response = client.get(f"/api/v1/positions/{event.id}/explain", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    body = response.json()

    technical_vote = next(v for v in body["agent_votes"] if v["domain"] == "technical")
    assert technical_vote["raw_confidence"] == 0.218
    assert len(technical_vote["weight_adjustments"]) == 2
    assert technical_vote["weight_adjustments"][0]["step"] == "benching_floor"

    long_summary = body["net_evidence_by_direction"]["LONG"]
    assert abs(long_summary["total_effective_influence"] - 0.295) < 1e-6
    assert {a["domain"] for a in long_summary["active_agents"]} == {"order_flow"}
    assert {a["domain"] for a in long_summary["suppressed_agents"]} == {"technical"}
    # En büyük gerçek etkiyi taşıyan (order_flow) listenin başında olmalı.
    assert long_summary["active_agents"][0]["domain"] == "order_flow"


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
    assert body["portfolio_confidence_discounts"] == []
    assert body["cross_asset_context"] == []
