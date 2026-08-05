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

# Faz 187: açık pozisyonları periyodik olarak kontrol edip süresi dolanları
# gerçek güncel fiyatla kapatır — "sürekli çalışan worker" ihtiyacının ilk
# gerçek örneği (celery beat ile, `celery -A services.celery_app beat`).
celery_app.conf.beat_schedule = {
    "close-due-positions-every-minute": {
        "task": "close_due_positions_task",
        "schedule": 60.0,
    },
    # Faz 190/194: "gerçek işlem alıyormuş gibi test başlasın" — AI'ın
    # sadece birisi dashboard'u açık tutunca değil, gerçekten bağımsız/
    # sürekli karar üretmesi. RiskEngine'in kendi cooldown'u (varsayılan
    # 60sn) gerçek işlem açma sıklığını zaten sınırlıyor. Faz 194'te tek
    # semboldan 10 sembollük bir watchlist'e (kripto + hisse/endeks/emtia,
    # her biri gerçek bir ağ çağrısı) geçince 30sn çok sıkı oldu — 90sn'ye
    # çıkarıldı, hâlâ "sürekli" ama art arda çağrıların kuyruğa yığılmasını
    # önlüyor.
    "run-trading-cycle-every-90s": {
        "task": "run_trading_cycle_task",
        "schedule": 90.0,
    },
}
