from fastapi.testclient import TestClient
from api.main import app
from contracts.auth import Role
from market_data.ingestion.data_provider import RoutingProvider
from tests.auth_helpers import make_authed_headers

client = TestClient(app)

def test_status():
    r = client.get("/api/v1/orchestrator/status", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_metrics():
    r = client.get("/api/v1/orchestrator/metrics", headers=make_authed_headers(Role.VIEWER))
    assert r.status_code == 200
    assert "memory_size" in r.json()

def test_cycle():
    r = client.post(
        "/api/v1/orchestrator/cycle",
        json={"seed": 42},
        headers=make_authed_headers(Role.OPERATOR),
    )
    assert r.status_code == 200
    data = r.json()
    assert "direction" in data
    assert "risk_verdict" in data


def test_module_singleton_uses_routing_provider_not_plain_binance():
    """Gerçek bulgu (2026-08-18) — kullanıcı raporu: Predictions sayfasında
    GC=F/SI=F/^IXIC/AAPL gibi Binance-dışı semboller hiç veri getirmiyordu.
    Sebep: bu router'daki modül-seviyesi _orchestrator singleton'ı
    data_provider vermeden kuruluyordu, varsayılan get_ohlcv_provider() düz
    BinanceProvider döndürüyor — sembol formatına bakmaksızın her şeyi
    Binance'e gönderiyordu. Gerçek trading cycle görevleri (services/tasks.py)
    zaten RoutingProvider kullanıyor; bu singleton'ın da aynısını kullandığını
    doğruluyor."""
    from api.rest.orchestrator import _orchestrator

    assert isinstance(_orchestrator.data_provider, RoutingProvider)
