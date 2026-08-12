"""services/orchestrator.py::_observe_decision_latency — Latency Monitoring
("ingestion→karar süresi") birim testleri."""
from datetime import UTC, datetime, timedelta

from prometheus_client.parser import text_string_to_metric_families

from observability.metrics import get_metrics
from services.orchestrator import _observe_decision_latency


def _histogram_count(symbol: str) -> float:
    text = get_metrics().decode()
    total = 0.0
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name != "decision_pipeline_latency_seconds_count":
                continue
            if sample.labels.get("symbol") == symbol:
                total += sample.value
    return total


def test_observes_a_real_positive_latency():
    symbol = "LATENCYTEST_POS"
    before = _histogram_count(symbol)
    last_bar = datetime.now(UTC) - timedelta(seconds=5)
    _observe_decision_latency(symbol, last_bar)
    assert _histogram_count(symbol) == before + 1


def test_naive_timestamp_is_treated_as_utc_not_a_crash():
    symbol = "LATENCYTEST_NAIVE"
    before = _histogram_count(symbol)
    last_bar = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=3)
    _observe_decision_latency(symbol, last_bar)
    assert _histogram_count(symbol) == before + 1


def test_a_future_timestamp_produces_negative_latency_and_is_not_observed():
    """Saat kayması ya da ileri tarihli sentetik veri — gerçek bir gecikme
    değil, Prometheus histogramına asla negatif bir gözlem yazılmamalı."""
    symbol = "LATENCYTEST_FUTURE"
    before = _histogram_count(symbol)
    last_bar = datetime.now(UTC) + timedelta(seconds=30)
    _observe_decision_latency(symbol, last_bar)
    assert _histogram_count(symbol) == before
