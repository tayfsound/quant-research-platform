"""Faz 165: Meta Optimizer Auto-Approval."""
from datetime import datetime, timedelta
from uuid import uuid4

from contracts.weight_approval import WeightApproval
from database.repositories.weight_approval_repository import WeightApprovalRepository
from database.session_factory import SessionFactory


def test_auto_reject_stale():
    """Eski pending approval'lar otomatik reject edilmeli."""
    approval = WeightApproval(
        id=uuid4(),
        proposed_weights={"technical": 1.5},
        previous_weights={"technical": 1.0},
        max_delta=0.1,
        status="pending",
        timestamp=datetime.now() - timedelta(hours=25),
        expires_at=datetime.now() - timedelta(hours=1),
    )

    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        repo.save(approval)

        count = repo.auto_reject_stale(max_age_seconds=3600 * 24)
        assert count >= 1

        pending = repo.get_pending(limit=50)
        assert all(a.id != approval.id for a in pending)


def test_approval_latency_metrics():
    """Onaylanmış approval'lar için latency metrikleri gerçek veriden hesaplanmalı."""
    approval = WeightApproval(
        id=uuid4(),
        proposed_weights={"technical": 1.2},
        previous_weights={"technical": 1.0},
        max_delta=0.1,
        status="approved",
        timestamp=datetime.now() - timedelta(seconds=120),
        decided_at=datetime.now(),
    )

    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        repo.save(approval)

        metrics = repo.approval_latency_metrics()
        assert "avg_seconds" in metrics
        assert "max_seconds" in metrics
        assert "p95_seconds" in metrics
        assert metrics["avg_seconds"] > 0
        assert metrics["max_seconds"] >= 120
