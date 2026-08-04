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
