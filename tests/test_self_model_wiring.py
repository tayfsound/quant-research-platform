"""GET /api/v1/self-model — Self-Model (öz-güvenilirlik), Cognitive Core 3.0.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only roadmap
modüllerini birer birer canlıya alalım — ECE'den sonraki Grup B adayı."""
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


def test_self_model_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/self-model/")
        assert response.status_code in (401, 403)


def test_self_model_endpoint_wires_real_signals_end_to_end():
    """Bu ortamda gerçek (paylaşılan dev DB) kapanmış işlem geçmişi var —
    overall_reliability'nin ne çıkacağı DB'nin o anki gerçek durumuna
    bağlı (bu yüzden sabit bir değer İDDİA EDİLMİYOR, calibration API
    testlerinin aynı gerçek-DB felsefesiyle). Burada asıl doğrulanan:
    uçtan uca hatasız çalışıyor VE kill switch kapalıyken kill_switch_
    active GERÇEKTEN False raporlanıyor (uydurma bir bayrak değil)."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with patch(
            "services.self_model_gatherer.load_position_risk_state",
            return_value={"consecutive_losses": 0, "kill_switch_consecutive_losses": 10},
        ):
            client = _client()
            response = client.get("/api/v1/self-model/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["overall_reliability"] in ("high", "degraded", "untrustworthy")
        assert "inputs" in result
        assert result["inputs"]["kill_switch_active"] is False


def test_self_model_flags_kill_switch_active():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with patch(
            "services.self_model_gatherer.load_position_risk_state",
            return_value={"consecutive_losses": 12, "kill_switch_consecutive_losses": 10},
        ):
            client = _client()
            response = client.get("/api/v1/self-model/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["overall_reliability"] == "untrustworthy"
        assert "kill_switch_active" in result["reliability_flags"]
        assert result["inputs"]["kill_switch_active"] is True


def test_self_model_computes_dsr_from_real_closed_trades():
    """20+ gerçek kapanmış işlem (hepsi kazanan, sabit %1 getiri) varken
    recent_dsr None DEĞİL, gerçekten hesaplanmış bir sayı olmalı."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"SMAPI{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for i in range(25):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=0.7, status="open",
                    entry_price=100.0, quantity=1.0, opened_at=now,
                )
                repo.persist(event)
                # Küçük gerçek varyasyonla %1 civarı kazanç — sabit
                # (varyanssız) seri compute_deflated_sharpe_ratio'da
                # fail-closed None döner, o yüzden hafif dalgalandırıldı.
                exit_price = 101.0 + (0.1 if i % 2 == 0 else -0.1)
                repo.close_position(
                    decision_id=str(event.id), exit_price=exit_price, pnl=1.0, closed_at=now,
                    outcome={"win": True},
                )

        from services.self_model_gatherer import gather_self_reliability_snapshot
        result = gather_self_reliability_snapshot()
        assert result["inputs"]["recent_dsr"] is not None


def test_get_cached_self_reliability_snapshot_shares_one_computation(monkeypatch):
    """Faz 310 — MetaStage'in (engines/cognitive_pipeline.py) çağırdığı
    TTL'li sürüm: bir trading cycle'ında watchlist'teki her sembol için
    tekrar tekrar pahalı hesaplama (2000 kararlık feature drift dahil)
    YAPILMAMALI — art arda çağrılar TEK bir gerçek hesaplamayı paylaşmalı."""
    import services.self_model_gatherer as gatherer_module

    gatherer_module._snapshot_cache = None
    calls = {"count": 0}
    real_gather = gatherer_module.gather_self_reliability_snapshot

    def counting_gather():
        calls["count"] += 1
        return real_gather()

    monkeypatch.setattr(gatherer_module, "gather_self_reliability_snapshot", counting_gather)

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        gatherer_module.get_cached_self_reliability_snapshot()
        gatherer_module.get_cached_self_reliability_snapshot()
        gatherer_module.get_cached_self_reliability_snapshot()

    assert calls["count"] == 1
    gatherer_module._snapshot_cache = None


def test_self_model_reports_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/self-model/reports")
        assert response.status_code in (401, 403)


def test_self_model_reports_returns_saved_snapshots():
    from contracts.self_model_report import SelfModelReport
    from database.repositories.self_model_report_repository import SelfModelReportRepository

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            report = SelfModelReport(
                result={"overall_reliability": "degraded", "reliability_flags": ["poor_calibration"], "inputs": {}},
            )
            SelfModelReportRepository(session).save(report)

        client = _client()
        response = client.get(
            "/api/v1/self-model/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        reports = response.json()["reports"]
        assert any(r["id"] == str(report.id) for r in reports)
        saved = next(r for r in reports if r["id"] == str(report.id))
        assert saved["result"]["overall_reliability"] == "degraded"


def test_refresh_self_model_report_task_saves_a_snapshot():
    from database.repositories.self_model_report_repository import SelfModelReportRepository
    from services.tasks import refresh_self_model_report_task

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        result = refresh_self_model_report_task()
        assert "overall_reliability" in result

        with SessionFactory.get_session() as session:
            saved = SelfModelReportRepository(session).get_latest()
        assert saved is not None
        assert saved["id"] == result["id"]
