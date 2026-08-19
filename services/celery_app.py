"""Sprint 27: Celery app — moves heavy operations (large replay batches)
off the request/response cycle onto async workers. Uses the
Redis instance that has been sitting in docker-compose.yml since before this
session with nothing actually using it — config/settings.py already had
REDIS_URL provisioned.
"""
from celery import Celery
from celery.signals import before_task_publish, task_postrun, task_prerun

from config import get_settings
from observability.logger import setup_logging

settings = get_settings()
# Faz 269-sonrası — bkz. api/main.py'deki AYNI bulgu: setup_logging()
# hiçbir yerden çağrılmıyordu. Worker/beat süreçlerinde de contextvars
# merge'in (distributed tracing) gerçekten aktif olması için burada da
# çağrılıyor.
setup_logging()

celery_app = Celery("qrp", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

# Faz 269-sonrası — kullanıcı isteği: distributed tracing (cycle_id).
# services/orchestrator.py::build_cognitive_context() her sembol için
# cycle_id'yi contextvars'a bind ediyor (o sembolün işlenmesi süresince
# TÜM log satırları otomatik taşır). Burdaki üç sinyal, standart Celery
# correlation-ID deseni: (1) bir task BAŞKA bir task'ı tetiklerse (bugün
# hiçbiri tetiklemiyor, ama services/tasks.py'ye ileride eklenebilir),
# yayınlanan mesajın header'ına o anki cycle_id'yi otomatik taşır; (2)
# her task başlarken worker sürecinin bir önceki task'tan kalma
# contextvars'ını temizleyip header'da bir cycle_id varsa onu bind eder,
# yoksa en azından celery_task_id/celery_task_name bağlar; (3) task
# bitince temizler — aynı worker süreci bir SONRAKİ tamamen alakasız
# task'ın loglarına eski cycle_id'yi asla sızdırmaz.
@before_task_publish.connect
def _propagate_cycle_id_to_task_headers(headers=None, **kwargs):
    if headers is None:
        return
    import structlog

    cycle_id = structlog.contextvars.get_contextvars().get("cycle_id")
    if cycle_id:
        headers["cycle_id"] = cycle_id


@task_prerun.connect
def _bind_task_context(task_id=None, task=None, **kwargs):
    import structlog

    structlog.contextvars.clear_contextvars()
    bind = {"celery_task_id": task_id, "celery_task_name": getattr(task, "name", None)}
    task_headers = getattr(getattr(task, "request", None), "headers", None) or {}
    if task_headers.get("cycle_id"):
        bind["cycle_id"] = task_headers["cycle_id"]
    structlog.contextvars.bind_contextvars(**bind)


@task_postrun.connect
def _clear_task_context(**kwargs):
    import structlog

    structlog.contextvars.clear_contextvars()

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

# Faz 268-sonrası — kritik bulgu (mimari inceleme, gerçek koda karşı
# doğrulandı): worker concurrency=1 ile TÜM task'lar (LLM denetimi, açık
# pozisyon kontrolü) AYNI tek kuyrukta bekliyordu. Bu, GERÇEKTEN yaşanmış
# bir olayla (HF Hub donması, embedding çağrısı celery worker'ı tamamen
# dondurmuş, kuyrukta 8320+ görev birikmişti — bkz. AI_MEMORY_SYSTEM/
# CURRENT_STATE.md) AYNI hata sınıfı: yavaş/ağ bağımlı bir görev
# (llm_system_audit_task ~1-2dk gerçek LLM çağrısı, refresh_llm_news_
# sentiment_task gerçek RSS/LLM çağrısı) çalışırken, GÜVENLİK KRİTİK
# close_due_positions_task
# (60sn'de bir açık pozisyonları stop/hedef/likidasyona göre kontrol
# eden görev) sırasını bekliyor — açık pozisyonlar bu süre boyunca
# kontrolsüz kalıyor. Yavaş/ağ-bağımlı görevler artık ayrı bir "slow"
# kuyruğuna yönlendiriliyor; bu kuyruğu SADECE ayrı bir worker tüketiyor
# (bkz. restart komutları), varsayılan kuyruktaki hızlı/kritik görevler
# hiçbir zaman onları beklemiyor.
celery_app.conf.task_routes = {
    "llm_system_audit_task": {"queue": "slow"},
    "refresh_llm_news_sentiment_task": {"queue": "slow"},
}

celery_app.autodiscover_tasks(["services"], related_name="tasks")

# Faz 187: açık pozisyonları periyodik olarak kontrol edip süresi dolanları
# gerçek güncel fiyatla kapatır — "sürekli çalışan worker" ihtiyacının ilk
# gerçek örneği (celery beat ile, `celery -A services.celery_app beat`).
celery_app.conf.beat_schedule = {
    "close-due-positions-every-minute": {
        "task": "close_due_positions_task",
        "schedule": 60.0,
    },
    # Shadow Mode (Faz 268-sonrası) — gerçek pozisyonlarla AYNI cadence,
    # ayrı bir tablo (shadow_positions) üzerinde çalışır.
    "close-due-shadow-positions-every-minute": {
        "task": "close_due_shadow_positions_task",
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
    # Faz 268-sonrası: Adaptive Barrier tablosu — retrain-agent-
    # confidence-models-daily ile AYNI ritim (günlük, ucuz bir SQL
    # sorgusu + lojistik olmayan bir ızgara taraması). Yetersiz veri
    # varsa no-op, kullanıcının hiçbir şeyi elle tetiklemesi gerekmiyor.
    "refresh-barrier-table-daily": {
        "task": "refresh_barrier_table_task",
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
    # Faz 268-sonrası: LLM tabanlı haber sentiment'i — provider'ın
    # _CACHE_TTL_SECONDS'ı (1800s/30dk) ile senkron ama biraz daha sık
    # (1500s/25dk) çalıştırılıyor ki önbellek süresi dolmadan bir sonraki
    # tazeleme zaten tamamlanmış olsun — canlı karar döngüsü hiçbir zaman
    # boş (None) bir önbellekle karşılaşmasın.
    "refresh-llm-news-sentiment": {
        "task": "refresh_llm_news_sentiment_task",
        "schedule": 1500.0,
    },
    # Faz 271 — kullanıcı isteği: "LLM'i her pozisyonda devreye sokmak
    # lazım... onay panelimi anlamlı kılmak için." Gerçek zamanlı bir
    # işlem kapısı değil (kullanıcının kendi tercihi: mekanik sistem
    # denetleyici LLM'den daha güvenilir bir karar verici) — periyodik
    # toplu denetim. 6 saatte bir: her gün 4 kez, gerçek bir LLM
    # çağrısı (~1-2dk, tool-calling ile 6 araca kadar) olduğu için
    # refresh-llm-news-sentiment'ten (ucuz) çok daha seyrek.
    "llm-system-audit-every-6h": {
        "task": "llm_system_audit_task",
        "schedule": 21600.0,
    },
    # Faz 268-sonrası — kullanıcı isteği: AI'dan tamamen yalıtık, test
    # amaçlı pump-fade stratejisi (bkz. services/pump_fade_strategy.py).
    # 48 saatlik "pump" penceresi dakikalar içinde önemli ölçüde değişmez;
    # 300+ USDT perpetual'ın her biri için gerçek bir Binance isteği
    # gerektirdiğinden (run_trading_cycle_task'ın 50 sembollük
    # watchlist'inden çok daha ağır bir tarama) 30 dakikada bir yeterli —
    # pump_fade_enabled=false (varsayılan) iken görev anında çıkar, hiçbir
    # yük oluşturmaz.
    "run-pump-fade-cycle-every-30m": {
        "task": "run_pump_fade_cycle_task",
        "schedule": 1800.0,
    },
    # Faz 268-sonrası — kullanıcı isteği: "Feature IC'yi karar hattına
    # bağlama." propose-agent-tuning-weekly ile AYNI ritim — feature IC'nin
    # zamanla anlamlı şekilde değişmesi günler değil haftalar sürer,
    # gerçek kapanmış işlem geçmişi üzerinde tekrar hesaplayan ucuz
    # olmayan bir işlem (100.000'e kadar satır çekip Pearson hesaplıyor).
    "refresh-feature-ic-report-weekly": {
        "task": "refresh_feature_ic_report_task",
        "schedule": 604800.0,
    },
    # Cognitive Core 2.0 / M4 — council'i hiç etkilemeyen ölçüm-only
    # roadmap modüllerinin canlıya alınan ilk adayı (ECE).
    "refresh-calibration-report-weekly": {
        "task": "refresh_calibration_report_task",
        "schedule": 604800.0,
    },
    # Cognitive Core 3.0 — Self-Model: ECE'den sonraki, council'i hiç
    # etkilemeyen ikinci ölçüm-only Grup B adayı.
    "refresh-self-model-report-weekly": {
        "task": "refresh_self_model_report_task",
        "schedule": 604800.0,
    },
    # Cognitive Core 4.0 — Causal Inference: Self-Model'den sonraki
    # üçüncü ölçüm-only Grup B adayı (Granger causality).
    "refresh-causal-inference-report-weekly": {
        "task": "refresh_causal_inference_report_task",
        "schedule": 604800.0,
    },
    # Cognitive Core 10.0 — Collective Intelligence: Causal Inference'tan
    # sonraki dördüncü ölçüm-only Grup B adayı (Condorcet'in Jüri Teoremi).
    "refresh-collective-intelligence-report-weekly": {
        "task": "refresh_collective_intelligence_report_task",
        "schedule": 604800.0,
    },
    # Cognitive Core 2.0 (Faz 469-493) — MAE/MFE Bootstrap Güven Aralığı:
    # Collective Intelligence'tan sonraki beşinci ölçüm-only Grup B adayı.
    "refresh-mae-mfe-confidence-report-weekly": {
        "task": "refresh_mae_mfe_confidence_report_task",
        "schedule": 604800.0,
    },
    # Faz 282 — kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte
    # canlıya alındı (hepsi council'i etkilemeyen, saf ölçüm/rapor
    # katmanları — kullanıcı "bunlar birbirinden alakasız modüller,
    # endişelenmemize gerek yok" diyerek tekli-aktivasyon disiplininden
    # bilinçli olarak istisna yaptı).
    "refresh-meta-learning-effectiveness-report-weekly": {
        "task": "refresh_meta_learning_effectiveness_report_task",
        "schedule": 604800.0,
    },
    "refresh-market-world-model-report-weekly": {
        "task": "refresh_market_world_model_report_task",
        "schedule": 604800.0,
    },
    "refresh-direction-prediction-v2-report-weekly": {
        "task": "refresh_direction_prediction_v2_report_task",
        "schedule": 604800.0,
    },
    "refresh-opportunity-quality-report-weekly": {
        "task": "refresh_opportunity_quality_report_task",
        "schedule": 604800.0,
    },
}
