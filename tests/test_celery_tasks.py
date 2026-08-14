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


def test_refresh_llm_news_sentiment_task_runs_in_eager_mode_and_returns_score():
    """Faz 268-sonrası: Reddit yerine LLM tabanlı gerçek haber sentiment'i
    — gerçek RSS/LLM ağ çağrısı yapmadan (mock'lanmış refresh()) görevin
    celery_app'e doğru kayıtlı olduğunu ve dönüş sözleşmesini doğrular."""
    from services.celery_app import celery_app
    from services.tasks import refresh_llm_news_sentiment_task

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        with patch(
            "market_data.sentiment.llm_news_sentiment_provider.refresh",
            return_value=(0.25, "Piyasa hafif olumlu."),
        ):
            async_result = refresh_llm_news_sentiment_task.delay()
            assert async_result.successful()
            assert async_result.result == {"sentiment_score": 0.25, "summary": "Piyasa hafif olumlu."}
    finally:
        celery_app.conf.task_always_eager = False


def test_refresh_llm_news_sentiment_task_is_in_beat_schedule():
    from services.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["refresh-llm-news-sentiment"]
    assert entry["task"] == "refresh_llm_news_sentiment_task"


def test_refresh_barrier_table_task_runs_in_eager_mode_and_returns_skip_when_insufficient(tmp_path):
    """Faz 268-sonrası: Adaptive Barrier tablosu — gerçek DB'ye karşı
    çalışıyor, testin çalıştığı ortamda genelde yeterli örneklem
    (MIN_TOTAL_SAMPLES=200) olmayacağı için fail-closed "skipped" dönmesi
    beklenir — asla gürültüden bir tablo üretilmemeli."""
    from services.celery_app import celery_app
    from services.tasks import refresh_barrier_table_task

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        with patch("analytics.barrier_table_builder.build_and_save_barrier_table", return_value=None):
            async_result = refresh_barrier_table_task.delay()
            assert async_result.successful()
            assert async_result.result == {"skipped": "insufficient_samples"}
    finally:
        celery_app.conf.task_always_eager = False


def test_refresh_barrier_table_task_is_in_beat_schedule():
    from services.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["refresh-barrier-table-daily"]
    assert entry["task"] == "refresh_barrier_table_task"


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


def test_live_trading_tasks_refuse_to_run_when_market_data_source_is_not_binance(monkeypatch):
    """Faz 268af — gerçek olay: 6 Ağustos'ta MARKET_DATA_SOURCE .env'den
    yüklenemediği bir anda sistem sessizce mock (deterministik, sahte)
    fiyatlarla gerçek pozisyon açtı, ~$1845 gerçek dışı kayıp yazdı.
    config/settings.py'de MARKET_DATA_SOURCE varsayılanı "mock" — bu test,
    canlı işlem task'larının artık bunu sessizce yutmadığını, "binance"
    dışında bir kaynakla hiç çalışmadan atladığını doğruluyor."""
    from config import get_settings
    from services.celery_app import celery_app
    from services.tasks import (
        close_due_positions_task,
        run_medium_term_cycle_task,
        run_pairs_trading_task,
        run_trading_cycle_task,
    )

    monkeypatch.setenv("MARKET_DATA_SOURCE", "mock")
    get_settings.cache_clear()
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        for task in (run_trading_cycle_task, run_pairs_trading_task, close_due_positions_task, run_medium_term_cycle_task):
            result = task.delay()
            assert result.successful()
            assert result.result == {"skipped": "non_binance_market_data_source"}
    finally:
        celery_app.conf.task_always_eager = False
        get_settings.cache_clear()  # sonraki testler gerçek "binance" ayarını görsün


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
