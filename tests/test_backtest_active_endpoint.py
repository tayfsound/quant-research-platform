"""Faz 268c — kullanıcı bulgusu: "arka planda hali hazırda çalışan bir
test olduğunda ben bunu göremiyorum." Önceki çözüm (dashboard'da task_id'yi
localStorage'a yazmak) sadece AYNI tarayıcıda, task'ı BAŞLATAN kişi için
işe yarıyordu. GET /backtest/active, celery worker'a GERÇEKTEN sorup o an
aktif olan backtest task'larını döndürüyor — kim/nereden başlattığından
bağımsız."""
from unittest.mock import MagicMock, patch

from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_active_endpoint_reports_a_real_running_backtest_task():
    fake_inspector = MagicMock()
    fake_inspector.active.return_value = {
        "worker1@host": [
            {"id": "abc-123", "name": "run_real_backtest_task", "args": ["BTCUSDT"], "time_start": 100.0},
            {"id": "xyz-789", "name": "some_other_unrelated_task", "args": [], "time_start": 50.0},
        ]
    }
    with patch("services.celery_app.celery_app.control.inspect", return_value=fake_inspector):
        client = _client()
        response = client.get("/api/v1/backtest/active", headers=make_authed_headers(Role.VIEWER))

    assert response.status_code == 200
    body = response.json()
    assert body["inspection_available"] is True
    task_ids = [t["task_id"] for t in body["active"]]
    assert "abc-123" in task_ids
    # Backtest'le ilgisi olmayan bir task (ör. trading cycle) listeye
    # sızmamalı — sadece gerçek backtest task isimleri filtreleniyor.
    assert "xyz-789" not in task_ids


def test_active_endpoint_reports_no_tasks_when_nothing_is_running():
    fake_inspector = MagicMock()
    fake_inspector.active.return_value = {}
    with patch("services.celery_app.celery_app.control.inspect", return_value=fake_inspector):
        client = _client()
        response = client.get("/api/v1/backtest/active", headers=make_authed_headers(Role.VIEWER))

    assert response.status_code == 200
    assert response.json() == {"active": [], "inspection_available": True}


def test_active_endpoint_fails_closed_when_worker_unreachable():
    """Worker'a ulaşılamıyorsa (ör. Redis geçici olarak erişilemez) 500
    ile patlamak yerine, UI'ın ayırt edebileceği bir "sorgulanamadı"
    durumu döndürülmeli — sessizce "hiçbir şey çalışmıyor" denmemeli."""
    with patch("services.celery_app.celery_app.control.inspect", side_effect=RuntimeError("broker down")):
        client = _client()
        response = client.get("/api/v1/backtest/active", headers=make_authed_headers(Role.VIEWER))

    assert response.status_code == 200
    body = response.json()
    assert body["inspection_available"] is False
    assert body["active"] == []
