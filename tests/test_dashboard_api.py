from fastapi.testclient import TestClient

from api.main import app
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers

client = TestClient(app)

def test_dashboard_latest():
    r = client.get("/api/v1/dashboard/latest", headers=make_authed_headers(Role.OPERATOR))
    assert r.status_code == 200
    assert "direction" in r.json()

def test_dashboard_health():
    r = client.get("/api/v1/dashboard/health", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_concept_drift_status_requires_auth():
    r = client.get("/api/v1/dashboard/concept-drift-status")
    assert r.status_code in (401, 403)


def test_concept_drift_status_returns_real_shape():
    """Faz 268-sonrası — kullanıcı isteği: "Concept Drift aktif olduğunda
    panelden göreyim." Paylaşılan test DB'sinin gerçek durumuna bağlı
    (available true/false ikisi de olabilir) — burada sadece sözleşmenin
    şekli doğrulanıyor, RiskEngine'in kendi mantığı zaten test_risk_state.
    py'de ayrıca doğrulanmış."""
    r = client.get("/api/v1/dashboard/concept-drift-status", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    body = r.json()
    assert "available" in body
    if body["available"]:
        assert "active" in body
        assert "baseline_win_rate" in body
        assert "recent_win_rate" in body
        assert "p_value" in body
        # Faz 268-sonrası — kullanıcı isteği: "sadece canlı modda aktif
        # olsun." "enforced", trading_mode=="live" olup olmadığını taşır
        # — test modunda drift tespit edilse bile pozisyon açmayı
        # ENGELLEMEZ, panel bunu ayırt edebilsin diye eklendi.
        assert "enforced" in body
        assert isinstance(body["enforced"], bool)
    else:
        assert "sample_size" in body


def test_concept_drift_reset_requires_auth():
    r = client.post("/api/v1/dashboard/concept-drift-status/reset")
    assert r.status_code in (401, 403)


def test_concept_drift_reset_requires_operator_role():
    r = client.post("/api/v1/dashboard/concept-drift-status/reset", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 403


def test_concept_drift_reset_sets_legacy_cutoff_and_status_reflects_it():
    """Faz 383 — kullanıcı isteği: "dashboard'daki uyarı balonuna kapatma
    butonu gelsin." Reset sonrası status endpoint'i AYNI cutoff'u
    okumalı — tek gerçek kaynak (bkz. api/rest/dashboard.py::
    reset_concept_drift docstring'i)."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        original_cutoff = AppSettingsRepository(session).get("concept_drift_legacy_cutoff_at")
    try:
        r = client.post("/api/v1/dashboard/concept-drift-status/reset", headers=make_authed_headers(Role.OPERATOR))
        assert r.status_code == 200
        body = r.json()
        assert "reset_at" in body
        assert body["reset_by"]

        status = client.get("/api/v1/dashboard/concept-drift-status", headers=make_authed_headers(Role.VIEWER))
        assert status.status_code == 200
        assert status.json()["reset_at"] == body["reset_at"]
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "concept_drift_legacy_cutoff_at", original_cutoff or "", updated_by="test",
            )
