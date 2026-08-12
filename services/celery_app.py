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
    # Faz 202: watchlist 10'dan 15 kaleme çıkınca (kullanıcı isteğiyle
    # yüksek hacimli kripto + altın-destekli token eklendi) 90sn'de sıraya
    # yığılma riski arttı — 120sn'ye çıkarıldı.
    "run-trading-cycle-every-120s": {
        "task": "run_trading_cycle_task",
        "schedule": 120.0,
    },
    # Faz 200: kointegrasyon/spread z-score, teknik göstergelerden çok daha
    # yavaş değişen istatistiksel ilişkiler — her 90sn'de kontrol etmenin
    # bir anlamı yok. 5 dakikada bir yeterli.
    "run-pairs-trading-every-5m": {
        "task": "run_pairs_trading_task",
        "schedule": 300.0,
    },
    # Faz 201: gerçek bulgu — IngestionPipeline.ingest_order_book() tam
    # çalışan bir metod olarak yazılmıştı ama hiçbir üretim kodu hiç
    # çağırmıyordu; order_book_snapshots tablosu ayların birikimiyle
    # sadece 16 satırdı, OrderFlowAgent (9 oy veren ajandan biri) neredeyse
    # hep boş veri görüp hep WAIT üretiyordu. Order book saniyeler içinde
    # değiştiği için trading cycle'dan (90sn) daha sık, 20sn'de bir.
    "ingest-order-book-every-20s": {
        "task": "ingest_order_book_task",
        "schedule": 20.0,
    },
    # Faz 207: aynı "ada" bulgusu — IngestionPipeline.ingest_candles()
    # (Market Overview dashboard sayfasının okuduğu tek kaynak,
    # market_snapshots tablosu) hiç periyodik çağrılmıyordu, sadece BTCUSDT
    # Faz 184'te elle bir kez dolduruldu. 1m çözünürlük dashboard'un
    # varsayılanı — 60sn'de bir yeterli, trading cycle kadar sık gerekmiyor.
    "ingest-candles-every-60s": {
        "task": "ingest_candles_task",
        "schedule": 60.0,
    },
    # Faz 204: ACT/REDUCE eşiklerinin kendi kendine kalibrasyonu — gerçek
    # kapalı işlem geçmişi gerektirdiği için (min. 20) yeterli veri
    # birikmeden hiçbir şey yapmıyor; ucuz bir sorgu olduğu için sık
    # (saatte bir) kontrol etmenin zararı yok.
    "optimize-thresholds-hourly": {
        "task": "optimize_thresholds_task",
        "schedule": 3600.0,
    },
    # Faz 264: kullanıcı isteği — ajan içi özellik ağırlıkları kayan
    # pencereyle (son N gerçek kapanmış işlem) düzenli aralıklarla
    # yeniden eğitiliyor, piyasa rejimi değiştikçe model de haftalar
    # değil GÜNLER içinde adapte olabilsin diye günlük (threshold
    # kalibrasyonuyla aynı ritim, ucuz bir işlem — sadece birkaç yüz
    # satırlık lojistik regresyon).
    "retrain-agent-confidence-models-daily": {
        "task": "retrain_agent_confidence_models_task",
        "schedule": 86400.0,
    },
    # Faz 229: kritik bulgu — WeightOptimizer'ın onay-gate'i (Faz 160-165)
    # dedup kontrolü olmadan üretimde 7000'den fazla bekleyen onay biriktirdi.
    # Dedup eklendi (has_pending()) ama zaten var olan/ilerideki süresi
    # dolmuş onayları temizleyen POST /weights/auto-reject hiç zamanlanmamıştı
    # — sadece elle çağrılabiliyordu. Günlük bir güvenlik ağı olarak eklendi.
    "auto-reject-stale-weight-approvals-daily": {
        "task": "auto_reject_stale_weight_approvals_task",
        "schedule": 86400.0,
    },
    # Faz 239-241: Online Meta-Learning (CMA-ES). retrain-agent-confidence-
    # models-daily'den (ucuz, lojistik regresyon) KASITLI OLARAK çok daha
    # seyrek — her çalıştığında yüzlerce/binlerce gerçek kayıt üzerinde
    # CMA-ES araması yapıyor (services/meta_learning_scheduler.py), haftalık
    # yeterli (ajan katsayılarının gerçek anlamda kayması günler değil
    # haftalar sürer).
    "propose-agent-tuning-weekly": {
        "task": "propose_agent_tuning_task",
        "schedule": 604800.0,
    },
    # Faz 259: kullanıcı isteği — orta-vadeli pozisyon katmanı. Günlük/4h
    # sinyal kısa-vadeli katmandan (120sn) çok daha yavaş değişiyor —
    # 4 saatte bir kontrol yeterli (medium_term_enabled=false iken görev
    # anında çıkıyor, gereksiz yük yok).
    "run-medium-term-cycle-every-4h": {
        "task": "run_medium_term_cycle_task",
        "schedule": 14400.0,
    },
}
