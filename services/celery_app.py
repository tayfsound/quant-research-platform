"""Sprint 27: Celery app — moves heavy operations (backtest runs, large
replay batches) off the request/response cycle onto async workers. Uses the
Redis instance that has been sitting in docker-compose.yml since before this
session with nothing actually using it — config/settings.py already had
REDIS_URL provisioned.
"""
from celery import Celery

from config import get_settings

settings = get_settings()

celery_app = Celery("qrp", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Only takes effect when task_always_eager is also on (tests/local dev,
    # e.g. `celery -A services.celery_app worker` isn't running) — a real
    # worker never runs in eager mode, so this doesn't affect production.
    # Set at the app level rather than per-test: toggling it after
    # celery_app.backend has already been lazily constructed doesn't
    # reliably take effect (the backend instance is cached).
    task_store_eager_result=True,
)

celery_app.autodiscover_tasks(["services"], related_name="tasks")
