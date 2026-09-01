"""GET /shadow/comparison — bkz. api/rest/shadow.py. Council vs Macro-Only
karşılaştırmasının AYNI ölçekte (fiyat getirisi %) döndüğünü doğrular."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.auth import Role
from contracts.shadow_position import ShadowPosition
from database.repositories.shadow_position_repository import ShadowPositionRepository
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_shadow_comparison_endpoint_returns_both_sides_with_sample_size_flag():
    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        position = ShadowPosition(
            source="macro", symbol=f"SHADOWAPI{uuid4().hex[:6]}", direction="LONG",
            entry_price=100.0, stop_loss_price=95.0, take_profit_price=110.0,
        )
        repo.open_position(position)
        repo.close_position(position.id, exit_price=110.0, exit_reason="take_profit", closed_at=datetime.now(UTC))

    # min_sample_size kasıtlı olarak çok büyük — bu test paylaşılan test
    # DB'sinde tekrar tekrar çalıştıkça birikmiş eski shadow pozisyonlardan
    # (gerçek olay: 106 kapanmış "macro" kaydı, varsayılan eşik 100'ü
    # aşmıştı) bağımsız, deterministik bir sample_size_sufficient=False
    # garantisi için.
    resp = _client().get(
        "/api/v1/shadow/comparison?min_sample_size=999999", headers=make_authed_headers(Role.VIEWER)
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["macro_only"]["closed_count"] >= 1
    assert body["macro_only"]["sample_size_sufficient"] is False
    assert "council" in body
    assert "win_rate" in body["council"]
    # Faz 400-devam — canonical evaluation cohort görünürlüğü.
    assert body["council"]["evaluation_window"]["limit"] == 100_000
    assert body["council"]["evaluation_window"]["exclude_experiment_buckets"] == ["pump_fade_v1"]


def test_shadow_comparison_endpoint_requires_auth():
    resp = _client().get("/api/v1/shadow/comparison")
    assert resp.status_code in (401, 403)
