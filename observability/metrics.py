"""Prometheus metrikleri — LLM, Risk, Sistem.

Sprint 14-15 (Faz 173-174): önceki metrikler (llm_*, risk_*, active_subprocesses,
queue_size) tanımlıydı ama hiçbir yerden .inc()/.observe()/.set() ile
çağrılmıyordu — Prometheus çıktısında isimleri görünür ama değerleri hep
sıfırdı, tamamen dekoratif. decisions_total/learning_updates_total/
api_*/db_query_latency_seconds eklendi VE gerçek kod yollarına bağlandı
(RiskEngine, RecordingStage, LearningLoop, FastAPI middleware,
DecisionPersistor) — bkz. CURRENT_STATE.md.
"""
import time

import psutil
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
cpu_usage_percent = Gauge(
    "cpu_usage_percent", "Process CPU usage percent"
)
memory_usage_percent = Gauge(
    "memory_usage_percent", "Process memory usage percent"
)

# Karar hızı (decisions_per_sec: Prometheus rate(decisions_total[1m]) ile türetilir)
decisions_total = Counter(
    "decisions_total", "Total decisions recorded", ["symbol", "action"]
)

# Öğrenme hızı
learning_updates_total = Counter(
    "learning_updates_total", "Total weight/memory learning updates applied"
)

# API
api_requests_total = Counter(
    "api_requests_total", "Total API requests", ["method", "path", "status"]
)
api_request_latency_seconds = Histogram(
    "api_request_latency_seconds", "API request latency", ["method", "path"]
)

# DB
db_query_latency_seconds = Histogram(
    "db_query_latency_seconds", "DB query/persist latency", ["operation"]
)

# Sağlık durumu
health_status = Gauge(
    "health_status", "System health (1=healthy, 0=unhealthy)"
)
health_status.set(1)

_process = psutil.Process()


def get_metrics() -> bytes:
    """Prometheus metrik endpoint'i için. CPU/RAM scrape anında ölçülür
    (arka plan thread'i yerine — Prometheus'un pull modeliyle tutarlı)."""
    cpu_usage_percent.set(_process.cpu_percent())
    memory_usage_percent.set(_process.memory_percent())
    return generate_latest(REGISTRY)
