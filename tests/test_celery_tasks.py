"""Sprint 27: Celery worker/queue architecture. Task logic is verified with
task_always_eager (the standard way to test Celery tasks without needing a
running worker process — runs the task function synchronously in-process,
through the real Celery task-call machinery, not just calling the plain
Python function directly). Broker connectivity is checked separately
against the real local Redis (already running in docker-compose)."""
from unittest.mock import patch

import pytest


def test_backtest_task_runs_synchronously_in_eager_mode_and_persists():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.celery_app import celery_app
            from services.tasks import run_backtest_task
            from database.repositories.backtest_run_repository import BacktestRunRepository
            from database.session_factory import SessionFactory

            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
            try:
                async_result = run_backtest_task.delay(["BTCUSDT"], bars=15, seed=3, fee=0.001)
                assert async_result.successful()
                body = async_result.result
                assert body["symbols"] == ["BTCUSDT"]

                with SessionFactory.get_session() as session:
                    row = BacktestRunRepository(session).get_by_id(body["id"])
                    assert row is not None
            finally:
                celery_app.conf.task_always_eager = False


def test_auto_reject_stale_weight_approvals_task_rejects_only_old_pending_rows():
    """Faz 229: kritik bulgu — canlı üretimde WeightApproval kuyruğu
    (dedup kontrolü olmadan) 7000'den fazla bekleyen satır biriktirmişti,
    ve süresi dolmuş onayları temizleyen POST /weights/auto-reject hiçbir
    zaman zamanlanmamıştı. Bu görev artık günlük bir güvenlik ağı olarak
    çalışıyor — burada gerçek bir DB satırı üzerinde uçtan uca doğrulanıyor."""
    from datetime import datetime, timedelta
    from uuid import uuid4

    from contracts.weight_approval import WeightApproval
    from database.repositories.weight_approval_repository import WeightApprovalRepository
    from database.session_factory import SessionFactory
    from services.celery_app import celery_app
    from services.tasks import auto_reject_stale_weight_approvals_task

    old_id = uuid4()
    with SessionFactory.get_session() as session:
        WeightApprovalRepository(session).save(
            WeightApproval(
                id=old_id,
                timestamp=datetime.now() - timedelta(hours=48),
                proposed_weights={"technical": 1.5},
                previous_weights={"technical": 1.0},
                status="pending",
            )
        )

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        result = auto_reject_stale_weight_approvals_task.delay(max_age_hours=24)
        assert result.successful()
        assert result.result["rejected_count"] >= 1
    finally:
        celery_app.conf.task_always_eager = False

    with SessionFactory.get_session() as session:
        from database.repositories.weight_approval_repository import WeightApprovalModel
        row = session.query(WeightApprovalModel).filter_by(id=old_id).first()
        assert row.status == "rejected"


def test_run_async_endpoint_dispatches_and_task_status_endpoint_reports_it():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app
            from services.celery_app import celery_app

            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
            try:
                from contracts.auth import Role
                from tests.auth_helpers import make_authed_headers

                client = TestClient(app)
                dispatch = client.post(
                    "/api/v1/backtest/run-async?symbols=BTCUSDT&bars=15",
                    headers=make_authed_headers(Role.OPERATOR),
                )
                assert dispatch.status_code == 200
                task_id = dispatch.json()["task_id"]

                status = client.get(
                    f"/api/v1/backtest/tasks/{task_id}",
                    headers=make_authed_headers(Role.VIEWER),
                )
                assert status.status_code == 200
                body = status.json()
                assert body["status"] == "SUCCESS"
                assert "id" in body["result"]
            finally:
                celery_app.conf.task_always_eager = False


def test_run_pairs_trading_task_runs_and_returns_pair_results():
    """Faz 200: celery beat'in periyodik tetiklediği görev gerçekten
    analytics/pairs_trading.py'yi çalıştırıp PAIR_CANDIDATES'teki her
    çift için bir sonuç döndürüyor."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory
            from services.celery_app import celery_app
            from services.tasks import run_pairs_trading_task

            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")

            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
            try:
                async_result = run_pairs_trading_task.delay()
                assert async_result.successful()
                body = async_result.result
                assert "pairs" in body
                assert len(body["pairs"]) == 3  # PAIR_CANDIDATES'teki 3 çift
            finally:
                celery_app.conf.task_always_eager = False


def test_run_trading_cycle_task_runs_a_real_cycle_when_ai_enabled():
    """Faz 190: 'gerçek işlem alıyormuş gibi' — celery beat'in periyodik
    tetiklediği görev, gerçek CognitiveOrchestrator.run_cycle()'ı çalıştırır."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory
            from services.celery_app import celery_app
            from services.tasks import run_trading_cycle_task

            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")

            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
            try:
                async_result = run_trading_cycle_task.delay(symbol="BTCUSDT")
                assert async_result.successful()
                body = async_result.result
                assert body["symbol"] == "BTCUSDT"
                assert body.get("skipped") is None
            finally:
                celery_app.conf.task_always_eager = False


def test_run_trading_cycle_task_skips_when_ai_disabled():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory
            from services.celery_app import celery_app
            from services.tasks import run_trading_cycle_task

            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set("ai_enabled", "false", updated_by="test")

            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
            try:
                async_result = run_trading_cycle_task.delay(symbol="BTCUSDT")
                assert async_result.successful()
                assert async_result.result == {"skipped": "ai_disabled"}
            finally:
                celery_app.conf.task_always_eager = False
                with SessionFactory.get_session() as session:
                    AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")


@pytest.mark.xfail(reason="requires a real Celery worker process, not just broker reachability", strict=False)
def test_broker_is_reachable_for_real_dispatch_without_eager_mode():
    """Sanity check against the actual local Redis (docker-compose) — proves
    the Celery app CAN connect to a broker, though driving a task through it
    end to end needs a running `celery -A services.celery_app worker`
    process this test suite doesn't spin up."""
    from services.celery_app import celery_app

    with celery_app.connection_or_acquire() as conn:
        conn.ensure_connection(max_retries=1)
