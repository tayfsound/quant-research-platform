"""WeightApproval E2E — real DB approval → real endpoint → real weight snapshot persisted."""
from uuid import uuid4

from contracts.auth import Role
from contracts.weight_approval import WeightApproval
from database.session_factory import SessionFactory
from database.repositories.weight_approval_repository import WeightApprovalRepository
from services.weight_repository import WeightRepository
from tests.auth_helpers import make_authed_headers


def test_approve_endpoint_applies_weights():
    """POST /weights/{id}/approve should flip DB status AND persist a real weight snapshot."""
    from fastapi.testclient import TestClient
    from api.main import app

    proposed = {"technical": 1.42, "macro": 0.87}

    approval = WeightApproval(
        id=uuid4(),
        proposed_weights=proposed,
        previous_weights={"technical": 1.0, "macro": 1.0},
        max_delta=0.5,
        status="pending",
    )
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).save(approval)

    client = TestClient(app)
    headers = make_authed_headers(Role.OPERATOR)
    response = client.post(f"/api/v1/weights/{approval.id}/approve", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["weights_applied"] is True

    with SessionFactory.get_session() as session:
        pending_after = WeightApprovalRepository(session).get_pending(limit=50)
        assert all(a.id != approval.id for a in pending_after)

    latest_snapshot = WeightRepository().get_latest()
    assert latest_snapshot is not None
    assert latest_snapshot.weights == proposed


def test_approve_endpoint_carries_regime_through_to_the_saved_snapshot():
    """Faz 268b — Regime-Aware Learning: bir rejim-özel WeightApproval
    onaylandığında, oluşan AgentWeightSnapshot da AYNI regime etiketini
    taşımalı — aksi halde onaylanan ağırlıklar yanlışlıkla global
    snapshot olarak kaydedilir ve karar anında hiçbir zaman regime-özel
    olarak seçilmez."""
    from fastapi.testclient import TestClient
    from api.main import app

    proposed = {"technical": 1.77}
    approval = WeightApproval(
        id=uuid4(),
        proposed_weights=proposed,
        previous_weights={"technical": 1.0},
        max_delta=0.5,
        regime="bullish_high",
        status="pending",
    )
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).save(approval)

    client = TestClient(app)
    headers = make_authed_headers(Role.OPERATOR)
    response = client.post(f"/api/v1/weights/{approval.id}/approve", headers=headers)
    assert response.status_code == 200

    with SessionFactory.get_session() as session:
        # get_pending only returns status=pending, so re-query directly.
        from database.repositories.weight_approval_repository import WeightApprovalModel
        pending_row = session.query(WeightApprovalModel).filter_by(id=approval.id).first()
        assert pending_row.status == "approved"
        assert pending_row.regime == "bullish_high"

    regime_snapshot = WeightRepository().get_latest(regime="bullish_high")
    assert regime_snapshot is not None
    assert regime_snapshot.weights == proposed
    assert regime_snapshot.regime == "bullish_high"


def test_pending_endpoint_includes_regime_field():
    from fastapi.testclient import TestClient
    from api.main import app

    approval = WeightApproval(
        id=uuid4(),
        proposed_weights={"technical": 1.3},
        previous_weights={"technical": 1.0},
        max_delta=0.2,
        regime="bearish_low",
        status="pending",
    )
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).save(approval)

    client = TestClient(app)
    response = client.get("/api/v1/weights/pending?limit=50")
    assert response.status_code == 200
    match = next(a for a in response.json()["pending"] if a["id"] == str(approval.id))
    assert match["regime"] == "bearish_low"


def test_pending_endpoint_returns_timestamp_and_max_delta_for_readable_ui():
    """Faz 224: kullanıcı bulgusu — "Approval a gelen onay sorularının
    formatı çok dağınık kod gibi görünüyor... yatay scrolling felan
    yapmadan onaylayamıyorum." Dashboard'un önceki/yeni/değişim tablosunu
    ve zaman damgasını gösterebilmesi için /pending artık previous/
    proposed'ın yanında timestamp ve max_delta'yı da döndürüyor."""
    from fastapi.testclient import TestClient
    from api.main import app

    approval = WeightApproval(
        id=uuid4(),
        proposed_weights={"technical": 1.3},
        previous_weights={"technical": 1.0},
        max_delta=0.2,
        status="pending",
    )
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).save(approval)

    client = TestClient(app)
    response = client.get("/api/v1/weights/pending?limit=50")
    assert response.status_code == 200
    rows = {r["id"]: r for r in response.json()["pending"]}
    row = rows[str(approval.id)]
    assert row["timestamp"] is not None
    assert row["max_delta"] == 0.2
    assert row["previous"] == {"technical": 1.0}
    assert row["proposed"] == {"technical": 1.3}
