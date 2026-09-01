"""GET /api/v1/calibration — Probability Calibration (ECE), Cognitive Core 2.0 / M4.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — ECE ilk aday."""
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


def test_calibration_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/calibration/")
        assert response.status_code in (401, 403)


def test_calibration_reflects_real_closed_trades_confidence_and_outcome():
    """%80 güvenle açılan 15 gerçek kapanmış işlem, GERÇEKTEN %80'i
    kazanıyor (12 win + 3 loss) -> mükemmel kalibre (ECE~0), fail-closed
    None DEĞİL (eşiği geçiyor).

    Faz 367-devam — kritik bulgu (2026-08-27): api/rest/calibration.py'nin
    endpoint'i BİLEREK filtresiz (`list_closed_trades(limit=100_000)`,
    "her istek gerçek kapanmış işlem geçmişinden taze hesaplanır") —
    üretimde doğru davranış ama paylaşılan quantdb_test'te BAŞKA
    yüzlerce testin bıraktığı gerçek (confidence, outcome) çiftleriyle
    karışıp bu testin kendi 15 mükemmel-kalibre satırını eziyordu (ECE
    zamanla 0'dan uzaklaşıp gerçek eşiği aşıyordu — shared test state
    bloat, bkz. proje hafızası). list_closed_trades bu test için
    izole ediliyor (SADECE bu testin kendi 15 satırı) — persist/
    close_position/gerçek HTTP round-trip hâlâ gerçek, sadece ECE
    hesabının GİRDİSİ izole."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"CALAPI{uuid4().hex[:8]}"
        now = datetime.now(UTC)

        isolated_trades = []
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for i in range(15):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=0.8, status="open",
                    entry_price=100.0, quantity=1.0, opened_at=now,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=101.0, pnl=1.0, closed_at=now,
                    outcome={"win": i < 12},  # 12/15 = %80, confidence'la eşleşiyor
                )
                isolated_trades.append({"confidence": 0.8, "outcome": {"win": i < 12}})

        client = _client()
        with patch(
            "database.repositories.decision_persistor.DecisionPersistor.list_closed_trades",
            return_value=isolated_trades,
        ):
            response = client.get("/api/v1/calibration/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()
        assert body["total_closed_trades"] == 15
        assert body["result"] is not None
        assert body["result"]["expected_calibration_error"] < 0.05
        # Faz 400-devam — canonical evaluation cohort görünürlüğü.
        assert body["evaluation_window"]["n_trades"] == 15
        assert body["evaluation_window"]["limit"] == 100_000


def test_calibration_reports_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/calibration/reports")
        assert response.status_code in (401, 403)


def test_calibration_reports_returns_saved_snapshots():
    from contracts.calibration_report import CalibrationReport
    from database.repositories.calibration_report_repository import CalibrationReportRepository

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            report = CalibrationReport(
                result={"expected_calibration_error": 0.07, "sample_size": 50, "bins": []},
                total_closed_trades=200,
            )
            CalibrationReportRepository(session).save(report)

        client = _client()
        response = client.get(
            "/api/v1/calibration/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        reports = response.json()["reports"]
        assert any(r["id"] == str(report.id) for r in reports)
        saved = next(r for r in reports if r["id"] == str(report.id))
        assert saved["total_closed_trades"] == 200
        assert saved["result"]["expected_calibration_error"] == 0.07
