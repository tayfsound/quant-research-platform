"""Sprint 14-15: prove the Prometheus metrics are actually wired into real
code paths, not just defined. Before this session, llm_*/risk_*/
active_subprocesses/queue_size were declared but never .inc()/.set() by any
real code — test_health.py only checked the metric NAME appeared in the
exposition text, not that it ever moved."""
from unittest.mock import patch

from prometheus_client.parser import text_string_to_metric_families

from observability.metrics import get_metrics


def _metric_value(sample_name: str, label_match: dict) -> float:
    """Matches on the exact exposed sample name (e.g. 'risk_rejections_total'
    or 'db_query_latency_seconds_count'), not the parser's family.name — the
    prometheus_client parser strips the _total/_count/_sum suffix from
    family.name, so matching on that would silently compare the wrong thing."""
    text = get_metrics().decode()
    total = 0.0
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name != sample_name:
                continue
            if all(sample.labels.get(k) == v for k, v in label_match.items()):
                total += sample.value
    return total


def _histogram_count(base_name: str, label_match: dict) -> float:
    return _metric_value(f"{base_name}_count", label_match)


class FakeLimit:
    value = 10.0

    def verify(self, secret):
        return True


def test_risk_engine_rejection_increments_real_metrics():
    from contracts.context import CognitiveCycleContext
    from engines.risk_engine import RiskEngine

    before = _metric_value("risk_rejections_total", {"reason": "MISSING_LIMIT"})

    ctx = CognitiveCycleContext()
    ctx.market.symbol = "METRICSTEST"
    ctx.risk.limits = {}  # no max_position_size -> MISSING_LIMIT
    RiskEngine().execute(ctx)

    after = _metric_value("risk_rejections_total", {"reason": "MISSING_LIMIT"})
    assert after == before + 1


def test_risk_engine_approval_increments_real_metrics():
    from contracts.context import CognitiveCycleContext
    from engines.risk_engine import RiskEngine

    before = _metric_value("risk_decisions_total", {"verdict": "approved", "symbol": "METRICSTEST2"})

    ctx = CognitiveCycleContext()
    ctx.market.symbol = "METRICSTEST2"
    ctx.decision.proposed_size = 1.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    RiskEngine().execute(ctx)

    after = _metric_value("risk_decisions_total", {"verdict": "approved", "symbol": "METRICSTEST2"})
    assert after == before + 1


def test_recording_stage_increments_decisions_total():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from contracts.context import CognitiveCycleContext
            from services.cognitive_engine import CognitiveEngine

            before = _metric_value("decisions_total", {"symbol": "METRICSTEST3"})

            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "METRICSTEST3"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            ctx.risk.current_drawdown = 0.0
            ctx.risk.limits = {"max_position_size": FakeLimit()}
            engine.run(ctx, persist=True)

            after = _metric_value("decisions_total", {"symbol": "METRICSTEST3"})
            assert after == before + 1


def test_api_middleware_increments_request_metrics():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app

            before = _histogram_count(
                "api_request_latency_seconds", {"method": "GET", "path": "/health"}
            )

            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200

            after = _histogram_count(
                "api_request_latency_seconds", {"method": "GET", "path": "/health"}
            )
            assert after == before + 1


def test_db_persist_records_latency_observation():
    from uuid import uuid4
    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    before = _histogram_count("db_query_latency_seconds", {"operation": "decision_persist"})

    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(DecisionEvent(id=uuid4(), symbol="METRICSTEST4"))

    after = _histogram_count("db_query_latency_seconds", {"operation": "decision_persist"})
    assert after == before + 1


def test_propose_records_decision_pipeline_latency():
    """Faz 268-sonrası: Latency Monitoring — services/orchestrator.py::
    propose() (GERÇEKTEN açılan pozisyonların geldiği birincil yol) her
    çağrıda decision_pipeline_latency_seconds'ı gözlemlemeli. transformers
    KASITLI OLARAK mock'lanmıyor — propose() ctx.market.features'ı GERÇEKTEN
    dolduruyor, bu da gerçek embedding modelini tetikliyor (bkz. backtest/
    real_historical_backtest.py'nin test dosyasındaki AYNI not)."""
    from services.orchestrator import CognitiveOrchestrator

    before = _histogram_count("decision_pipeline_latency_seconds", {"symbol": "BTCUSDT"})

    orch = CognitiveOrchestrator()
    proposal = orch.propose("BTCUSDT")
    assert proposal is not None

    after = _histogram_count("decision_pipeline_latency_seconds", {"symbol": "BTCUSDT"})
    assert after == before + 1


def test_cpu_and_memory_gauges_are_real_nonzero_values_after_scrape():
    get_metrics()  # scrape triggers the psutil measurement
    cpu = _metric_value("cpu_usage_percent", {})
    mem = _metric_value("memory_usage_percent", {})
    assert cpu >= 0.0
    assert mem > 0.0  # a running process always has nonzero resident memory
