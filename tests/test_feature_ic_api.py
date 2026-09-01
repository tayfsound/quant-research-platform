"""GET /api/v1/feature-ic — Online Feature Selection (Information Coefficient)."""
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


def test_feature_ic_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/feature-ic/")
        assert response.status_code in (401, 403)


def test_feature_ic_reflects_real_closed_trades_with_feature_contributions():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"FICAPI{uuid4().hex[:8]}"
        now = datetime.now(UTC)

        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for i in range(25):
                entry = 100.0
                exit_price = 101.0 + i * 0.1  # her zaman yükseliyor, artan miktarda
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=0.6, status="open",
                    entry_price=entry, quantity=1.0, opened_at=now,
                    agent_opinions=[{
                        "agent_id": "quant_agent_v1", "domain": "quant",
                        "feature_contributions": {f"ictest_signal_{symbol}": 1.0 + i * 0.01},
                    }],
                )
                repo.persist(event)
                repo.close_position(decision_id=str(event.id), exit_price=exit_price, pnl=1.0, closed_at=now)

        client = _client()
        response = client.get(
            "/api/v1/feature-ic/", params={"min_sample_size": 20}, headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        features = response.json()["features"]
        key = f"ictest_signal_{symbol}"
        assert key in features
        assert features[key]["ic"] > 0.9
        assert features[key]["sample_size"] == 25
        assert features[key]["agent_domain"] == "quant"
        # Faz 400-devam — canonical evaluation cohort görünürlüğü. Paylaşılan
        # quantdb_test'te başka testlerin de satırları olabileceği için
        # kesin sayı yerine sadece alanın varlığı/mantıklılığı doğrulanıyor.
        evaluation_window = response.json()["evaluation_window"]
        assert evaluation_window["n_trades"] >= 25
        assert evaluation_window["limit"] == 100_000


def test_feature_ic_reports_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/feature-ic/reports")
        assert response.status_code in (401, 403)


def test_feature_ic_reports_returns_saved_snapshots():
    """Faz 268-sonrası — kullanıcı isteği: "Feature IC'yi karar hattına
    bağlama." Canlı / uç noktası her zaman O ANKİ durumu gösterir; bu
    test /reports'un GERÇEKTEN kaydedilmiş (services/tasks.py::refresh_
    feature_ic_report_task'ın ürettiği) geçmişi döndürdüğünü doğruluyor."""
    from contracts.feature_ic_report import FeatureICReport
    from database.repositories.feature_ic_report_repository import FeatureICReportRepository

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            report = FeatureICReport(
                features={"test_feature_xyz": {"ic": 0.42, "p_value": 0.01, "sample_size": 30, "agent_domain": "quant"}},
                total_closed_trades=123,
            )
            FeatureICReportRepository(session).save(report)

        client = _client()
        response = client.get(
            "/api/v1/feature-ic/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        reports = response.json()["reports"]
        assert any(r["id"] == str(report.id) for r in reports)
        saved = next(r for r in reports if r["id"] == str(report.id))
        assert saved["total_closed_trades"] == 123
        assert saved["features"]["test_feature_xyz"]["ic"] == 0.42
