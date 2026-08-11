"""Health check endpoint testleri."""
from fastapi.testclient import TestClient

from api.main import app
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_ready():
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

def test_live():
    resp = client.get("/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"

def test_metrics():
    # 3. taraf inceleme bulgusu (5.2) — /metrics auth'suzdu, API 0.0.0.0'a
    # bağlı (LAN'a açık) olduğu için aynı ağdaki biri metrikleri
    # görebiliyordu. Artık diğer korumalı endpoint'lerle aynı auth şart.
    resp = client.get("/metrics", headers=make_authed_headers(Role.VIEWER))
    assert resp.status_code == 200
    assert "llm_requests_total" in resp.text


def test_metrics_requires_auth():
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_signal_health_reports_real_freshness_per_module():
    """Faz 230: kullanıcı isteği — Faz 203-211'deki 7 katmanlı sessiz-hata
    zinciri ("sistem çalışıyor görünüyor ama hiç gerçek işlem açmıyor")
    bir daha sessizce yaşanmasın diye eklenen izleme. Gerçek DB'ye karşı —
    quantdb_test'te candle/order-book/decisions verisi zaten var (diğer
    testlerden), bu yüzden şekli/anahtarları doğruluyoruz, mutlak
    healthy/unhealthy durumunu değil (o, testin ne zaman çalıştığına bağlı)."""
    resp = client.get("/health/signals")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "healthy" in body
    for key in ("candle_ingestion", "order_book_ingestion", "trading_cycle", "zombie_wait"):
        assert key in body["checks"]
