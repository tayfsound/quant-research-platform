"""Prometheus metrikleri — LLM, Risk, Sistem."""
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info, generate_latest

from version import MODEL_VERSION, PROMPT_VERSION, SYSTEM_VERSION

# Sistem bilgisi
system_info = Info("quant_platform", "Platform version info")
system_info.info({
    "system_version": SYSTEM_VERSION,
    "prompt_version": PROMPT_VERSION,
    "model_version": MODEL_VERSION,
})

# LLM metrikleri
llm_requests_total = Counter(
    "llm_requests_total", "Total LLM requests", ["status", "symbol"]
)
llm_latency_seconds = Histogram(
    "llm_latency_seconds", "LLM request latency", ["symbol"]
)
llm_timeouts_total = Counter(
    "llm_timeouts_total", "Total LLM timeouts", ["symbol"]
)
llm_parse_failures_total = Counter(
    "llm_parse_failures_total", "Total JSON parse failures", ["symbol"]
)

# Risk metrikleri
risk_decisions_total = Counter(
    "risk_decisions_total", "Total risk decisions", ["verdict", "symbol"]
)
risk_rejections_total = Counter(
    "risk_rejections_total", "Total risk rejections", ["reason"]
)

# Sistem metrikleri
active_subprocesses = Gauge(
    "active_subprocesses", "Currently active subprocesses"
)
queue_size = Gauge(
    "queue_size", "Current event queue size"
)

# Sağlık durumu
health_status = Gauge(
    "health_status", "System health (1=healthy, 0=unhealthy)"
)
health_status.set(1)


def get_metrics() -> bytes:
    """Prometheus metrik endpoint'i için."""
    return generate_latest(REGISTRY)
