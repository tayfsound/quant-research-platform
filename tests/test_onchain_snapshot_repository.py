"""Faz 196: OnChainSnapshotRepository — 24 saatlik delta hesaplaması."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from database.repositories.onchain_snapshot_repository import OnChainSnapshotRepository
from database.session_factory import SessionFactory


def test_delta_24h_is_none_when_no_older_snapshot_exists():
    metric = f"test_metric_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = OnChainSnapshotRepository(session)
        assert repo.get_delta_24h(metric, current_value=100.0) is None


def test_delta_24h_computes_real_difference_against_an_old_snapshot():
    metric = f"test_metric_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = OnChainSnapshotRepository(session)
        repo.save(metric, 1000.0, time=datetime.now(UTC) - timedelta(hours=25))
        delta = repo.get_delta_24h(metric, current_value=1150.0)

    assert delta == 150.0


def test_delta_24h_ignores_a_snapshot_that_is_too_recent():
    metric = f"test_metric_{uuid4().hex[:8]}"
    with SessionFactory.get_session() as session:
        repo = OnChainSnapshotRepository(session)
        repo.save(metric, 1000.0, time=datetime.now(UTC) - timedelta(hours=1))
        delta = repo.get_delta_24h(metric, current_value=1150.0)

    assert delta is None
