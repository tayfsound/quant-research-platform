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
