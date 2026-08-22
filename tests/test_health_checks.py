"""Sprint 28: /ready must actually reflect DB reachability, not just always
say yes — a K8s readiness probe wired to a fake check is worse than no
probe at all (false confidence)."""
from unittest.mock import patch


def test_ready_returns_200_when_db_reachable():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["checks"]["database"] is True


def test_ready_returns_503_when_db_unreachable():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from fastapi.testclient import TestClient

        import observability.health as health_module
        from api.main import app

        client = TestClient(app)
        with patch.object(health_module, "_check_database", return_value=False):
            response = client.get("/ready")
            assert response.status_code == 503
            assert response.json()["status"] == "not_ready"


def test_live_does_not_depend_on_database():
    """Liveness must stay green even if the DB check would fail — killing a
    healthy process over a DB outage it can't fix is the wrong response."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from fastapi.testclient import TestClient

        import observability.health as health_module
        from api.main import app

        client = TestClient(app)
        with patch.object(health_module, "_check_database", return_value=False):
            response = client.get("/live")
            assert response.status_code == 200
            assert response.json()["status"] == "alive"
