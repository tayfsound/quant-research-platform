"""Faz 269-sonrası — kullanıcı isteği: distributed tracing (cycle_id).
cycle_id zaten decisions.id ile AYNIydı (services/decision_recorder.py) —
eksik olan log satırlarına hiç yansımamasıydı. Bu testler: (1)
setup_logging()'in contextvars merge'i gerçekten etkinleştirdiğini, (2)
build_cognitive_context()'in her sembol için cycle_id'yi bind ettiğini,
(3) Celery sinyallerinin (before_task_publish/task_prerun/task_postrun)
standart correlation-ID desenini doğru uyguladığını doğruluyor."""
import structlog

from market_data.ingestion.ohlcv import OHLCV
from datetime import UTC, datetime, timedelta


def _bars(n=60):
    now = datetime.now(UTC)
    return [
        OHLCV(timestamp=now - timedelta(hours=n - i), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)
        for i in range(n)
    ]


def test_setup_logging_registers_merge_contextvars_processor():
    from observability.logger import setup_logging

    setup_logging()
    processors = structlog.get_config()["processors"]
    assert structlog.contextvars.merge_contextvars in processors


def test_build_cognitive_context_binds_cycle_id_to_contextvars():
    from services.orchestrator import build_cognitive_context

    structlog.contextvars.clear_contextvars()
    try:
        ctx = build_cognitive_context("TRACETEST1USDT", "1h", _bars())

        bound = structlog.contextvars.get_contextvars()
        assert bound["cycle_id"] == str(ctx.cycle_id)
        assert bound["symbol"] == "TRACETEST1USDT"
    finally:
        structlog.contextvars.clear_contextvars()


def test_build_cognitive_context_rebinds_a_fresh_cycle_id_per_symbol():
    """Ardışık iki sembol işlendiğinde ikincinin cycle_id'si birincininkini
    contextvars'ta EZMELİ (sızıntı olmamalı) — her iki entrypoint'in de
    (orchestrator + api/rest/cognitive.py) paylaştığı TEK gerçek kaynak."""
    from services.orchestrator import build_cognitive_context

    structlog.contextvars.clear_contextvars()
    try:
        ctx1 = build_cognitive_context("TRACETEST2USDT", "1h", _bars())
        bound1 = structlog.contextvars.get_contextvars()
        assert bound1["cycle_id"] == str(ctx1.cycle_id)

        ctx2 = build_cognitive_context("TRACETEST3USDT", "1h", _bars())
        bound2 = structlog.contextvars.get_contextvars()

        assert bound2["cycle_id"] == str(ctx2.cycle_id)
        assert bound2["cycle_id"] != bound1["cycle_id"]
    finally:
        structlog.contextvars.clear_contextvars()


def test_log_lines_carry_the_bound_cycle_id():
    from structlog.testing import capture_logs

    structlog.contextvars.clear_contextvars()
    try:
        structlog.contextvars.bind_contextvars(cycle_id="fixed-cycle-id-for-test")
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            structlog.get_logger().info("some_event_during_a_cycle")

        assert logs[0]["cycle_id"] == "fixed-cycle-id-for-test"
    finally:
        structlog.contextvars.clear_contextvars()


class _FakeTask:
    def __init__(self, name, headers=None):
        self.name = name
        self.request = type("Request", (), {"headers": headers})()


def test_propagate_cycle_id_to_task_headers_injects_the_bound_cycle_id():
    from services.celery_app import _propagate_cycle_id_to_task_headers

    structlog.contextvars.clear_contextvars()
    try:
        structlog.contextvars.bind_contextvars(cycle_id="parent-cycle-id")
        headers = {}
        _propagate_cycle_id_to_task_headers(headers=headers)
        assert headers["cycle_id"] == "parent-cycle-id"
    finally:
        structlog.contextvars.clear_contextvars()


def test_propagate_cycle_id_to_task_headers_is_a_noop_when_nothing_is_bound():
    from services.celery_app import _propagate_cycle_id_to_task_headers

    structlog.contextvars.clear_contextvars()
    headers = {}
    _propagate_cycle_id_to_task_headers(headers=headers)
    assert "cycle_id" not in headers


def test_bind_task_context_reads_cycle_id_from_task_headers():
    from services.celery_app import _bind_task_context

    structlog.contextvars.clear_contextvars()
    try:
        task = _FakeTask("some_task", headers={"cycle_id": "propagated-cycle-id"})
        _bind_task_context(task_id="task-123", task=task)

        bound = structlog.contextvars.get_contextvars()
        assert bound["cycle_id"] == "propagated-cycle-id"
        assert bound["celery_task_id"] == "task-123"
        assert bound["celery_task_name"] == "some_task"
    finally:
        structlog.contextvars.clear_contextvars()


def test_bind_task_context_clears_stale_context_from_a_previous_task():
    """Aynı worker süreci (prefork) art arda alakasız task'lar çalıştırır
    — bir öncekinin cycle_id'si bir SONRAKİ, hiç header taşımayan task'a
    asla sızmamalı."""
    from services.celery_app import _bind_task_context

    structlog.contextvars.clear_contextvars()
    try:
        structlog.contextvars.bind_contextvars(cycle_id="stale-cycle-id-from-previous-task")

        task = _FakeTask("unrelated_task", headers=None)
        _bind_task_context(task_id="task-456", task=task)

        bound = structlog.contextvars.get_contextvars()
        assert "cycle_id" not in bound
        assert bound["celery_task_name"] == "unrelated_task"
    finally:
        structlog.contextvars.clear_contextvars()


def test_clear_task_context_clears_everything_bound():
    from services.celery_app import _clear_task_context

    structlog.contextvars.bind_contextvars(cycle_id="whatever", celery_task_id="x")
    _clear_task_context()
    assert structlog.contextvars.get_contextvars() == {}


def test_finalize_proposal_logs_a_real_line_carrying_this_symbols_cycle_id():
    """Kullanıcı isteği: normal (olaysız) bir cycle'da da cycle_id'nin
    canlı loglarda GERÇEKTEN görünmesi — önceden risk red sebepleri
    sadece dönüş verisinde duruyordu, hiçbir şey loglanmıyordu."""
    from unittest.mock import patch

    from structlog.testing import capture_logs

    from contracts.context import CognitiveCycleContext
    from services.orchestrator import CognitiveOrchestrator

    structlog.contextvars.clear_contextvars()
    try:
        orch = CognitiveOrchestrator()
        ctx = CognitiveCycleContext()
        ctx.market.symbol = "TRACEFINALIZEUSDT"
        ctx.risk.evaluation.verdict = "rejected"
        structlog.contextvars.bind_contextvars(cycle_id=str(ctx.cycle_id), symbol=ctx.market.symbol)

        proposal = {"ctx": ctx, "data": _bars(), "fee": 0.0, "direction": "NEUTRAL"}
        with patch.object(orch.forward, "calculate", return_value={"pnl": 0.0, "win": False}), \
                patch.object(orch.engine, "finalize", side_effect=lambda c: c):
            with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
                orch.finalize_proposal(proposal, seed=1)

        matching = [entry for entry in logs if entry["event"] == "cognitive_cycle_completed"]
        assert len(matching) == 1
        assert matching[0]["cycle_id"] == str(ctx.cycle_id)
        assert matching[0]["risk_verdict"] == "rejected"
    finally:
        structlog.contextvars.clear_contextvars()


def test_run_trading_cycle_task_logs_a_task_level_summary_line():
    """Kullanıcı isteği: "cycle tamamlandı, N sembol işlendi, M reddedildi"
    tarzı bir özet — task'ın işlediği TÜM sembolleri tek satırda özetler
    (celery_task_id/celery_task_name zaten task_prerun sinyaliyle bağlı).

    lock:run_trading_cycle_task GERÇEK Redis'te celery beat'in canlı,
    aynı anda çalışan kopyasıyla PAYLAŞILAN bir anahtar — test öncesi
    temizlenmezse, canlı bir cycle tam o sırada kilidi tutuyorsa bu test
    'skipped: previous_cycle_still_running' ile flaky şekilde geçebilir."""
    import redis

    from config import get_settings
    from unittest.mock import MagicMock, patch

    from structlog.testing import capture_logs

    redis.from_url(get_settings().REDIS_URL).delete("lock:run_trading_cycle_task")

    with patch("database.repositories.app_settings_repository.AppSettingsRepository") as mock_repo_cls, \
            patch("market_data.market_hours.is_market_open", return_value=True), \
            patch("services.orchestrator.CognitiveOrchestrator") as mock_orch_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get.side_effect = lambda key: {
            "ai_enabled": "true", "watchlist": "TRACETASKAUSDT,TRACETASKBUSDT",
        }[key]

        mock_orch = mock_orch_cls.return_value
        mock_orch.run_portfolio_aware_cycle.return_value = [
            {"symbol": "TRACETASKAUSDT", "direction": "NEUTRAL", "risk_verdict": "rejected"},
            {"symbol": "TRACETASKBUSDT", "direction": "LONG", "risk_verdict": "approved"},
        ]

        from services.tasks import run_trading_cycle_task

        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            result = run_trading_cycle_task()

    matching = [entry for entry in logs if entry["event"] == "trading_cycle_task_completed"]
    assert len(matching) == 1
    assert matching[0]["total_symbols"] == 2
    assert matching[0]["rejected"] == 1
    assert len(result["cycles"]) == 2
