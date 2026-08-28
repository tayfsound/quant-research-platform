"""GET /api/v1/feature-relationship — Faz 368 uçtan uca kablo testleri."""
from datetime import UTC, datetime
from unittest.mock import patch
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


def test_feature_relationship_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/feature-relationship/")
        assert response.status_code in (401, 403)


def test_feature_relationship_reflects_real_closed_trades_with_a_redundant_pair():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"FRWIRE{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        feat_a = f"frtest_a_{symbol}"
        feat_b = f"frtest_b_{symbol}"

        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for i in range(25):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=0.6, status="open",
                    entry_price=100.0, quantity=1.0, opened_at=now,
                    agent_opinions=[{
                        "agent_id": "quant_agent_v1", "domain": "quant",
                        "feature_contributions": {feat_a: 1.0 + i * 0.01, feat_b: 1.0 + i * 0.01},
                    }],
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=101.0 + i * 0.1, pnl=1.0, closed_at=now
                )

        client = _client()
        response = client.get("/api/v1/feature-relationship/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()
        key = "|".join(sorted([feat_a, feat_b]))
        assert key in body["redundancy"]
        assert body["redundancy"][key]["correlation"] > 0.999
        assert body["redundancy"][key]["sample_size"] == 25


def test_feature_relationship_reports_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/feature-relationship/reports")
        assert response.status_code in (401, 403)


def test_feature_relationship_reports_returns_saved_snapshots():
    from contracts.feature_relationship_report import FeatureRelationshipReport
    from database.repositories.feature_relationship_report_repository import (
        FeatureRelationshipReportRepository,
    )

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            report = FeatureRelationshipReport(
                redundancy={"a|b": {"correlation": 0.95, "sample_size": 40}},
                conditional_ic={"a": {"raw_ic": 0.5, "conditional_ic_given": {"b": None}}},
                total_closed_trades=77,
            )
            FeatureRelationshipReportRepository(session).save(report)

        client = _client()
        response = client.get(
            "/api/v1/feature-relationship/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        reports = response.json()["reports"]
        assert any(r["id"] == str(report.id) for r in reports)
        saved = next(r for r in reports if r["id"] == str(report.id))
        assert saved["total_closed_trades"] == 77
        assert saved["redundancy"]["a|b"]["correlation"] == 0.95
