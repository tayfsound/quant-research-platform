"""Sprint 27: Celery tasks for heavy, request-response-unfriendly work."""
from services.celery_app import celery_app


class _CycleLock:
    """Faz 268-sonrası — kritik bulgu, kullanıcı bulgusu: watchlist 207
    sembole çıkınca run_trading_cycle_task'ın (120sn'de bir, tek worker,
    concurrency=1) tek bir çalışması 120 saniyeden çok daha uzun sürmeye
    başladı — celery beat yine de her 120sn'de bir YENİ bir kopyasını
    kuyruğa eklemeye devam etti, hiçbiri gerçekten bitmediği için kuyruk
    11.900+ göreve kadar tıkandı (backtest dahil hiçbir görev sırasına
    asla gelemedi). Bu basit Redis SETNX kilidi, bir önceki çalışma hâlâ
    sürüyorsa yenisinin sessizce atlanmasını (kuyruğa hiç girmemesini)
    sağlıyor — watchlist boyutundan bağımsız, bu hata sınıfı bir daha
    asla oluşamaz. TTL, worker çökerse kilidin sonsuza dek takılı
    kalmaması için bir güvenlik tavanı (gerçek çalışma süresinden çok
    daha uzun tutuluyor)."""

    def __init__(self, key: str, ttl_seconds: int):
        self.key = key
        self.ttl_seconds = ttl_seconds
        self._acquired = False

    def __enter__(self) -> bool:
        import redis

        from config import get_settings

        self._client = redis.from_url(get_settings().REDIS_URL)
        self._acquired = bool(self._client.set(self.key, "1", nx=True, ex=self.ttl_seconds))
        return self._acquired

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._acquired:
            self._client.delete(self.key)


def _real_market_data_source_or_none() -> str | None:
    """Faz 268af — gerçek olay: 6 Ağustos 21:27-21:46 arası, MARKET_DATA_
    SOURCE'un .env'den yüklenemediği bir anda (muhtemelen bir celery
    worker restart sırasında) sistem sessizce config/settings.py'nin
    varsayılanı olan "mock" (deterministik, sahte, seed=42) veriyle 4
    sembolde (ADAUSDT/XAUTUSDT/XRPUSDT/PAXGUSDT) GERÇEK pozisyon açtı —
    hepsi aynı anlamsız ~$32.375 fiyattan, toplam ~$1845 gerçek dışı
    kayıp. Hata FIRLATMADI, sessizce devam etti — bu projenin baştan beri
    benimsediği "fail-fake yerine fail-closed" ilkesine tam ters.

    Canlı işlem açan/kapatan task'lar artık başta bunu kontrol ediyor:
    MARKET_DATA_SOURCE gerçekten "binance" değilse (herhangi bir sebeple
    .env yanlış/eksik yüklenmişse) o döngüyü sessizce mock veriyle
    yürütmek yerine hiç çalıştırmıyor, sadece kritik seviyede loglayıp
    atlıyor."""
    from config import get_settings

    settings = get_settings()
    if settings.MARKET_DATA_SOURCE != "binance":
        import structlog
        structlog.get_logger().critical(
            "live_trading_task_blocked_non_binance_market_data_source",
            market_data_source=settings.MARKET_DATA_SOURCE,
        )
        return None
    return settings.MARKET_DATA_SOURCE


@celery_app.task(name="run_trading_cycle_task")
def run_trading_cycle_task(symbol: str | None = None) -> dict:
    """Faz 190/194: "gerçek işlem alıyormuş gibi" — AI'ın sadece birisi
    dashboard'u açık tutunca değil, gerçekten sürekli, bağımsız çalışması.
    celery beat tarafından periyodik tetiklenir (bkz. celery_app.py:
    beat_schedule). ai_enabled=false ise RiskEngine zaten reddeder ama
    burada erken çıkmak gereksiz bir cycle'ı (embedding dahil) baştan
    engelliyor. symbol verilmezse (celery beat'in gerçek çağrı şekli)
    kullanıcının Settings'te belirlediği watchlist'teki TÜM enstrümanlar
    (kripto + endeks/emtia/hisse) sırayla işlenir."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider, get_provider_for_symbol
    from market_data.market_hours import is_market_open
    from services.orchestrator import CognitiveOrchestrator

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        ai_enabled = settings_repo.get("ai_enabled") == "true"
        watchlist = [s.strip() for s in settings_repo.get("watchlist").split(",") if s.strip()]

    if not ai_enabled:
        return {"skipped": "ai_disabled"}

    if symbol:
        # Tek-sembol açık çağrı (test/manuel tetik) — eski, basit davranış.
        if not is_market_open(symbol):
            return {"symbol": symbol, "skipped": "market_closed"}
        orch = CognitiveOrchestrator(data_provider=get_provider_for_symbol(symbol))
        result = orch.run_cycle(symbol=symbol)
        return {
            "symbol": result.get("symbol"),
            "direction": result.get("direction"),
            "risk_verdict": result.get("risk_verdict"),
            "risk_reasons": result.get("risk_reasons"),
        }

    # celery beat'in gerçek çağrı şekli: kapalı piyasaları eleyip kalan
    # watchlist'i TEK bir orchestrator/RoutingProvider ile toplu işliyoruz —
    # Faz 199: bu, run_portfolio_aware_cycle'ın 2+ sembol eşzamanlı yönlü
    # öneri gördüğünde gerçek portföy VaR'ına göre ölçeklendirme yapabilmesi
    # için şart (tek tek ayrı orchestrator'larla mümkün değil).
    with _CycleLock("lock:run_trading_cycle_task", ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": "previous_cycle_still_running"}

        open_symbols = [s for s in watchlist if is_market_open(s)]
        closed_symbols = [s for s in watchlist if s not in open_symbols]

        orch = CognitiveOrchestrator(data_provider=RoutingProvider())
        cycles = orch.run_portfolio_aware_cycle(open_symbols) if open_symbols else []
        cycles += [{"symbol": s, "skipped": "market_closed"} for s in closed_symbols]

    # Faz 269-sonrası — kullanıcı isteği: distributed tracing'in görünür
    # olması için task-seviyesi bir özet log satırı — celery_task_id
    # (task_prerun sinyaliyle zaten bağlı) üzerinden bu task çalışmasının
    # TÜM sembollerini tek satırda özetler. Her sembolün KENDİ cycle_id'si
    # ayrıca cognitive_cycle_completed satırında (orchestrator.py) var —
    # burası N sembol / kaç reddedildi özeti, tek bir cycle_id'ye
    # indirgenemeyecek toplu bir görünüm.
    import structlog

    structlog.get_logger().info(
        "trading_cycle_task_completed",
        total_symbols=len(cycles),
        rejected=sum(1 for c in cycles if c.get("risk_verdict") == "rejected"),
        skipped=sum(1 for c in cycles if c.get("skipped")),
    )

    return {"cycles": [
        {
            "symbol": c.get("symbol"),
            "direction": c.get("direction"),
            "risk_verdict": c.get("risk_verdict"),
            "risk_reasons": c.get("risk_reasons"),
            "skipped": c.get("skipped"),
        }
        for c in cycles
    ]}


@celery_app.task(name="run_medium_term_cycle_task")
def run_medium_term_cycle_task() -> dict:
    """Faz 259: kullanıcı isteği — orta-vadeli pozisyon katmanı, kısa-
    vadeli run_trading_cycle_task'tan (120sn) bağımsız, çok daha seyrek
    çalışan ayrı bir döngü (bkz. celery_app.py:beat_schedule — günlük/4h
    sinyal zaten bu kadar sık değişmiyor, her 120sn'de kontrol etmenin
    anlamı yok). medium_term_enabled=false ise (varsayılan) erken çıkar —
    kısa-vadeli sistemi hiç etkilemez, tamamen opt-in."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from market_data.market_hours import is_market_open
    from services.orchestrator import CognitiveOrchestrator

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        if settings_repo.get("medium_term_enabled") != "true":
            return {"skipped": "medium_term_disabled"}
        ai_enabled = settings_repo.get("ai_enabled") == "true"
        watchlist = [s.strip() for s in settings_repo.get("watchlist").split(",") if s.strip()]

    if not ai_enabled:
        return {"skipped": "ai_disabled"}

    open_symbols = [s for s in watchlist if is_market_open(s)]

    with _CycleLock("lock:run_medium_term_cycle_task", ttl_seconds=1800) as acquired:
        if not acquired:
            return {"skipped": "previous_cycle_still_running"}

        orch = CognitiveOrchestrator(data_provider=RoutingProvider())
        cycles = orch.run_medium_term_cycle(open_symbols) if open_symbols else []

    return {"cycles": [
        {
            "symbol": c.get("symbol"),
            "direction": c.get("direction"),
            "risk_verdict": c.get("risk_verdict"),
            "risk_reasons": c.get("risk_reasons"),
            "error": c.get("error"),
        }
        for c in cycles
    ]}


@celery_app.task(name="optimize_thresholds_task")
def optimize_thresholds_task() -> dict:
    """Faz 204: MetaStage'in act_threshold/reduce_threshold'ını gerçek
    kapalı işlem geçmişinden kendi kendine kalibre eder (bkz. services/
    threshold_optimizer.py). Yeterli veri (min. 20 kapalı işlem) yoksa
    hiçbir şey değiştirmez — icat edilmiş bir sayı yazılmaz."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from services.threshold_optimizer import compute_suggested_thresholds

    suggestion = compute_suggested_thresholds()
    if suggestion is None:
        return {"skipped": "insufficient_closed_trades"}

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        repo.set("act_threshold", str(suggestion["act_threshold"]), updated_by="threshold_optimizer")
        repo.set("reduce_threshold", str(suggestion["reduce_threshold"]), updated_by="threshold_optimizer")

    return suggestion


@celery_app.task(name="refresh_llm_news_sentiment_task")
def refresh_llm_news_sentiment_task() -> dict:
    """Faz 268-sonrası — kullanıcı isteği: Reddit sentiment (Devvit
    politikası nedeniyle) kapalıydı, yerine gerçek RSS başlıklarını
    NVIDIA LLM'e özetleten/puanlayan yeni kaynak (bkz. market_data/
    sentiment/llm_news_sentiment_provider.py). refresh() gerçek bir LLM
    çağrısı yaptığı için (~90s'ye kadar) SADECE bu periyodik görevden
    çağrılmalı, canlı karar döngüsünden değil — orası sadece get_cached()
    okur."""
    from market_data.sentiment.llm_news_sentiment_provider import refresh

    score, summary = refresh()
    if score is None:
        return {"skipped": "no_score"}
    return {"sentiment_score": score, "summary": summary}


@celery_app.task(name="llm_system_audit_task")
def llm_system_audit_task() -> dict:
    """Faz 271 — kullanıcı isteği: "LLM'i her pozisyonda devreye sokmak
    lazım... onay panelimi anlamlı kılmak için." Gerçek zamanlı bir
    işlem kapısı DEĞİL (kullanıcının kendi tercihi: mekanik sistem daha
    iyi kalibre edilirse daha iyi sonuç verir, LLM denetleyici rolünde
    kalsın) — periyodik olarak son dönem karar geçmişini toplu gözden
    geçirip, bulduğu somut sorunları code_change_proposals kuyruğuna
    (insan onaylı) düşürür. Gerçek bir LLM çağrısı yaptığı için (~1-2dk)
    SADECE bu periyodik görevden çağrılmalı, canlı karar döngüsünden değil."""
    from services.llm_system_audit import run_system_audit

    return run_system_audit()


@celery_app.task(name="retrain_agent_confidence_models_task")
def retrain_agent_confidence_models_task() -> dict:
    """Faz 264: kullanıcı isteği — ajan içi özellik ağırlıkları (RSI/trend/
    momentum vb.) elle yazılmış sabitler yerine gerçek sonuçlardan
    öğrenilsin, AMA tek seferlik/donuk bir model olmasın — "piyasa sürekli
    devinim içinde" gerekçesiyle kayan pencereyle (son N gerçek kapanmış
    işlem) düzenli aralıklarla yeniden eğitiliyor. Yetersiz veri varsa
    (bkz. train_confidence_model min_samples) o domain için hiçbir şey
    değiştirmez — eski model (varsa) geçerliliğini korur, icat edilmiş
    bir model kaydedilmez."""
    from services.agent_confidence_model import (
        FEATURE_SCHEMAS,
        ConfidenceModelRepository,
        train_confidence_model,
    )

    repo = ConfidenceModelRepository()
    results = {}
    for domain in FEATURE_SCHEMAS:
        model = train_confidence_model(domain)
        if model is None:
            results[domain] = {"skipped": "insufficient_samples"}
            continue
        repo.save(model)
        results[domain] = {
            "sample_count": model.sample_count,
            "test_accuracy": model.test_accuracy,
            "test_auc": model.test_auc,
            "baseline_correctness_rate": model.baseline_correctness_rate,
        }
    return results


@celery_app.task(name="refresh_barrier_table_task")
def refresh_barrier_table_task() -> dict:
    """Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine'i
    RiskTargetStage'e wire ettik ("kesin unuturum" kararıyla ayrı bir
    açık/kapalı anahtarı yok, güvenlik veri şartından geliyor). Bu görev,
    gerçek kapanmış işlemler MIN_TOTAL_SAMPLES'a (200) ulaşınca tabloyu
    otomatik kurup kaydeder — kullanıcı hiçbir şeyi elle tetiklemek
    zorunda kalmaz. Yetersiz veri varsa (bkz. build_and_save_barrier_
    table) hiçbir şey değiştirmez, eski tablo (varsa) korunur."""
    from analytics.barrier_table_builder import build_and_save_barrier_table

    table = build_and_save_barrier_table()
    if table is None:
        return {"skipped": "insufficient_samples"}
    return {"buckets": len(table)}


@celery_app.task(name="auto_reject_stale_weight_approvals_task")
def auto_reject_stale_weight_approvals_task(max_age_hours: float = 24) -> dict:
    """Faz 229: kritik bulgu — canlı üretimde WeightOptimizer.optimize()/
    propose_weights() dedup kontrolü olmadan her büyük ağırlık
    değişikliğinde koşulsuzca yeni bir WeightApproval satırı oluşturuyordu
    (7000'den fazla bekleyen onay birikti, gerçek ağırlıklar saatlerce
    donuk kaldı). Dedup kontrolü eklendi (bkz. WeightApprovalRepository.
    has_pending()) ama bu, süresi dolmuş (`expires_at` geçmiş, insan hiç
    karar vermemiş) onayları otomatik reddeden POST /weights/auto-reject
    hiçbir zaman zamanlanmamıştı — sadece elle çağrılabiliyordu. Artık
    günlük bir güvenlik ağı olarak çalışıyor."""
    from database.session_factory import SessionFactory
    from database.repositories.weight_approval_repository import WeightApprovalRepository

    with SessionFactory.get_session() as session:
        repo = WeightApprovalRepository(session)
        rejected_count = repo.auto_reject_stale(max_age_seconds=max_age_hours * 3600)
    return {"rejected_count": rejected_count, "max_age_hours": max_age_hours}


@celery_app.task(name="propose_agent_tuning_task")
def propose_agent_tuning_task() -> dict:
    """Faz 239-241: Online Meta-Learning (CMA-ES). retrain_agent_confidence_
    models_task'tan (günlük, ucuz — birkaç yüz satırlık lojistik regresyon)
    KASITLI OLARAK ayrı ve daha SEYREK — CMA-ES her çalıştığında yüzlerce/
    binlerce kayıt üzerinde tekrar tekrar TechnicalAgent.analyze() çağıran
    gerçek bir arama, ucuz bir işlem değil. Fail-closed: yetersiz veri ya
    da walk-forward geçmezse hiçbir şey oluşturmaz (bkz.
    services/meta_learning_scheduler.py::propose_technical_agent_tuning)."""
    from services.meta_learning_scheduler import propose_technical_agent_tuning

    approval = propose_technical_agent_tuning()
    if approval is None:
        return {"proposed": False}
    return {
        "proposed": True,
        "agent_id": approval.agent_id,
        "sharpe_improvement": approval.sharpe_improvement,
        "sample_count": approval.sample_count,
    }


@celery_app.task(name="refresh_feature_ic_report_task")
def refresh_feature_ic_report_task() -> dict:
    """Faz 268-sonrası — kullanıcı isteği: "Feature IC'yi karar hattına
    bağlama" yol haritası maddesi. analytics/feature_ic.py::
    compute_feature_ic() zaten gerçek zamanlı çalışıyordu (GET
    /feature-ic/) ama hiçbir GEÇMİŞİ yoktu — "IC zamanla nasıl değişti"
    sorusu cevaplanamıyordu. Bu görev periyodik (haftalık) bir anlık
    görüntüyü contracts/feature_ic_report.py::FeatureICReport olarak
    kaydediyor — llm_system_audit_task/llm_audit_runs (Faz 271) ile AYNI
    desen. SADECE ölçüm/kayıt — hiçbir feature'ı otomatik pasifleştirmiyor
    (compute_feature_ic'in kendi ilkesiyle aynı: "AI kendi skorlama
    mantığını otomatik gevşetemez/değiştiremez")."""
    from analytics.feature_ic import compute_feature_ic
    from contracts.feature_ic_report import FeatureICReport
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.feature_ic_report_repository import FeatureICReportRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=100_000)
        features = compute_feature_ic(closed_trades)
        report = FeatureICReport(features=features, total_closed_trades=len(closed_trades))
        FeatureICReportRepository(session).save(report)

    return {"id": str(report.id), "feature_count": len(features), "total_closed_trades": len(closed_trades)}


@celery_app.task(name="refresh_calibration_report_task")
def refresh_calibration_report_task() -> dict:
    """Cognitive Core 2.0 / M4 — kullanıcı isteği: council'i hiç etkilemeyen,
    ölçüm-only roadmap modüllerini birer birer canlıya (izlenebilir hale)
    alalım, ilk aday olarak ECE seçildi (en düşük eşik, en düşük risk).
    analytics/calibration_uncertainty.py::compute_expected_calibration_error()
    zaten gerçek zamanlı çalışıyordu (GET /calibration/) ama hiçbir GEÇMİŞİ
    yoktu. feature_ic_report_task/llm_audit_run ile AYNI desen. SADECE
    ölçüm/kayıt — hiçbir ajanın confidence'ını otomatik düzeltmiyor."""
    from analytics.calibration_uncertainty import (
        compute_expected_calibration_error,
        extract_predictions_from_closed_trades,
    )
    from contracts.calibration_report import CalibrationReport
    from database.repositories.calibration_report_repository import CalibrationReportRepository
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(limit=100_000)
        predictions = extract_predictions_from_closed_trades(closed_trades)
        result = compute_expected_calibration_error(predictions)
        report = CalibrationReport(result=result, total_closed_trades=len(closed_trades))
        CalibrationReportRepository(session).save(report)

    return {
        "id": str(report.id),
        "ece": (result or {}).get("expected_calibration_error"),
        "sample_size": (result or {}).get("sample_size"),
        "total_closed_trades": len(closed_trades),
    }


@celery_app.task(name="refresh_self_model_report_task")
def refresh_self_model_report_task() -> dict:
    """Cognitive Core 3.0 — kullanıcı isteği: council'i hiç etkilemeyen,
    ölçüm-only roadmap modüllerini birer birer canlıya alalım. ECE'den
    sonraki Grup B adayı: Self-Model (analytics/self_model.py, Faz
    769-800) — kalibrasyon, DSR, kill switch, feature/concept drift gibi
    ZATEN GERÇEKTEN hesaplanan bağımsız sinyalleri TEK bir öz-değerlendirme
    anlık görüntüsünde birleştirir. calibration_report_task ile AYNI desen
    — SADECE ölçüm/kayıt, hiçbir karar/risk parametresini değiştirmiyor."""
    from contracts.self_model_report import SelfModelReport
    from database.repositories.self_model_report_repository import SelfModelReportRepository
    from database.session_factory import SessionFactory
    from services.self_model_gatherer import gather_self_reliability_snapshot

    result = gather_self_reliability_snapshot()
    with SessionFactory.get_session() as session:
        report = SelfModelReport(result=result)
        SelfModelReportRepository(session).save(report)

    return {"id": str(report.id), "overall_reliability": result.get("overall_reliability")}


@celery_app.task(name="refresh_causal_inference_report_task")
def refresh_causal_inference_report_task() -> dict:
    """Cognitive Core 4.0 — kullanıcı isteği: council'i hiç etkilemeyen,
    ölçüm-only roadmap modüllerini birer birer canlıya alalım. Self-
    Model'den sonraki Grup B adayı: Causal Inference (analytics/causal_
    inference.py, Faz 861-900) — Granger causality, sistemdeki diğer
    TÜM ilişki sinyallerinin (korelasyon tabanlı) aksine standart bir
    "öngörücü nedensellik" testi. SADECE ölçüm/kayıt — hiçbir karar/risk
    parametresini değiştirmiyor."""
    from contracts.causal_inference_report import CausalInferenceReport
    from database.repositories.causal_inference_report_repository import CausalInferenceReportRepository
    from database.session_factory import SessionFactory
    from services.causal_inference_gatherer import gather_causal_relationships

    result = gather_causal_relationships()
    with SessionFactory.get_session() as session:
        report = CausalInferenceReport(result=result)
        CausalInferenceReportRepository(session).save(report)

    return {"id": str(report.id), "significant_relationship_count": len(result.get("significant_relationships", []))}


@celery_app.task(name="refresh_agent_combination_reliability_report_task")
def refresh_agent_combination_reliability_report_task() -> dict:
    """Faz 331 — kullanıcı isteği (harici bir AI incelemesinin önerdiği,
    defalarca gündeme gelip ertelenen bir madde): Opportunity Quality
    (Faz 569-593) KAÇ ajanın anlaştığını win_rate ile ilişkilendiriyordu,
    bu HANGİ ajan İKİLİLERİNİN birlikte anlaştığını ilişkilendiriyor
    (analytics/agent_combination_reliability.py). SADECE ölçüm/kayıt —
    hiçbir ajan ağırlığını/karar mantığını değiştirmiyor."""
    from contracts.agent_combination_reliability_report import AgentCombinationReliabilityReport
    from database.repositories.agent_combination_reliability_report_repository import (
        AgentCombinationReliabilityReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.agent_combination_reliability_gatherer import gather_agent_combination_reliability

    result = gather_agent_combination_reliability()
    with SessionFactory.get_session() as session:
        report = AgentCombinationReliabilityReport(result=result)
        AgentCombinationReliabilityReportRepository(session).save(report)

    return {"id": str(report.id), "pair_count": len(result.get("pairs", []))}


@celery_app.task(name="refresh_collective_intelligence_report_task")
def refresh_collective_intelligence_report_task() -> dict:
    """Cognitive Core 10.0 — kullanıcı isteği: council'i hiç etkilemeyen,
    ölçüm-only roadmap modüllerini birer birer canlıya alalım. Causal
    Inference'tan sonraki Grup B adayı: Collective Intelligence
    (analytics/collective_intelligence.py, Faz 971-1000) — Condorcet'in
    Jüri Teoremi ile 10-ajanlı council'in toplamının GERÇEKTEN en iyi
    tekil ajandan daha isabetli olup olmadığını doğrular. SADECE ölçüm/
    kayıt — hiçbir ajan ağırlığını değiştirmiyor."""
    from contracts.collective_intelligence_report import CollectiveIntelligenceReport
    from database.repositories.collective_intelligence_report_repository import (
        CollectiveIntelligenceReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.collective_intelligence_gatherer import gather_collective_intelligence

    result = gather_collective_intelligence()
    with SessionFactory.get_session() as session:
        report = CollectiveIntelligenceReport(result=result)
        CollectiveIntelligenceReportRepository(session).save(report)

    condorcet = result.get("condorcet") or {}
    return {"id": str(report.id), "collective_beats_best_individual": condorcet.get("collective_beats_best_individual")}


@celery_app.task(name="refresh_mae_mfe_confidence_report_task")
def refresh_mae_mfe_confidence_report_task() -> dict:
    """Cognitive Core 2.0 (Faz 469-493) — kullanıcı isteği: council'i hiç
    etkilemeyen, ölçüm-only roadmap modüllerini birer birer canlıya
    alalım. Collective Intelligence'tan sonraki Grup B adayı: MAE/MFE
    Bootstrap Güven Aralığı (analytics/mae_mfe_scientific.py) — mevcut
    nokta tahminlerinin (p90 MAE gibi) GERÇEK belirsizliğini raporlar.
    SADECE ölçüm/kayıt — hiçbir SL/TP kararını değiştirmiyor."""
    from contracts.mae_mfe_confidence_report import MaeMfeConfidenceReport
    from database.repositories.mae_mfe_confidence_report_repository import (
        MaeMfeConfidenceReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.mae_mfe_confidence_gatherer import gather_mae_mfe_confidence

    result = gather_mae_mfe_confidence()
    with SessionFactory.get_session() as session:
        report = MaeMfeConfidenceReport(result=result)
        MaeMfeConfidenceReportRepository(session).save(report)

    return {"id": str(report.id), "total_trades": result.get("total_trades"), "group_count": len(result.get("confidence_intervals") or {})}


@celery_app.task(name="ingest_order_book_task")
def ingest_order_book_task() -> dict:
    """Faz 201: gerçek bulgu — market_data/ingestion/pipeline.py::
    IngestionPipeline.ingest_order_book() tam çalışan, gerçek bir metod
    olarak yazılmıştı (best bid/ask, imbalance, spread_bps — Order Flow
    ajanının gerçekten ihtiyaç duyduğu her şey) ama hiçbir üretim kodu onu
    hiç çağırmıyordu — order_book_snapshots tablosunda ayların birikimi
    sadece 16 satır vardı, OrderFlowAgent neredeyse her zaman boş/varsayılan
    veri görüp hep WAIT üretiyordu. Sadece Binance sembolleri için (order
    book derinliği yfinance'te yok) — kripto olmayan semboller için
    OrderFlowAgent'ın nötr kalması dürüst, eksik değil."""
    import asyncio

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from exchange_gateway.binance.adapter import BinanceAdapter
    from market_data.ingestion.data_provider import looks_like_binance_pair
    from market_data.ingestion.pipeline import IngestionPipeline

    with SessionFactory.get_session() as session:
        watchlist = [
            s.strip() for s in AppSettingsRepository(session).get("watchlist").split(",") if s.strip()
        ]

    crypto_symbols = [s for s in watchlist if looks_like_binance_pair(s)]
    pipeline = IngestionPipeline(BinanceAdapter())

    results = {}
    for sym in crypto_symbols:
        try:
            results[sym] = asyncio.run(pipeline.ingest_order_book(sym))
        except Exception as exc:
            results[sym] = {"error": str(exc)}

    return {"ingested": results}


@celery_app.task(name="ingest_candles_task")
def ingest_candles_task() -> dict:
    """Faz 207: gerçek bulgu — ingest_order_book_task ile birebir aynı
    "ada" deseni. IngestionPipeline.ingest_candles() (market_snapshots
    tablosuna gerçek Binance mumu yazan, tam çalışan bir metod — Market
    Overview dashboard sayfasının /market-data/ohlcv endpoint'i SADECE bu
    tabloyu okuyor) hiçbir zaman periyodik çağrılmıyordu. Tabloda BTCUSDT
    için 300'er barlık gerçek veri vardı (Faz 184'te elle bir kez
    çalıştırılmış) ama watchlist 15 kaleme çıktığında geri kalan 14 sembol
    hiç eklenmedi — kullanıcı Market sayfasında BTC dışında hiçbir grafik
    göremiyordu, boş değil, hiç veri yoktu. Trading cycle'ın kendi OHLCV
    çekişi (RoutingProvider) tamamen ayrı bir yol — bu tabloya hiç
    yazmıyor, o yüzden council'in gerçekten trade alması bu tabloyu
    beslemiyordu. Sadece Binance sembolleri (yfinance'te candle var ama bu
    pipeline binance-specific; kripto olmayanlar için Market sayfası hâlâ
    boş kalır — ayrı bir iş)."""
    import asyncio

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from exchange_gateway.binance.adapter import BinanceAdapter
    from market_data.ingestion.data_provider import looks_like_binance_pair
    from market_data.ingestion.pipeline import IngestionPipeline

    with SessionFactory.get_session() as session:
        watchlist = [
            s.strip() for s in AppSettingsRepository(session).get("watchlist").split(",") if s.strip()
        ]

    crypto_symbols = [s for s in watchlist if looks_like_binance_pair(s)]
    pipeline = IngestionPipeline(BinanceAdapter())

    results = {}
    for sym in crypto_symbols:
        try:
            results[sym] = asyncio.run(pipeline.ingest_candles(sym, timeframe="1m", limit=100))
        except Exception as exc:
            results[sym] = {"error": str(exc)}

    return {"ingested": results}


@celery_app.task(name="run_pump_fade_cycle_task")
def run_pump_fade_cycle_task() -> dict:
    """Faz 268-sonrası — kullanıcı isteği: AI konsey/confidence sisteminden
    tamamen yalıtık, test amaçlı mekanik bir strateji (bkz. services/
    pump_fade_strategy.py). run_trading_cycle_task/run_medium_term_cycle_task
    gibi ai_enabled'a hiç bakmıyor — kendi bağımsız pump_fade_enabled
    anahtarıyla (PumpFadeStrategy.run_cycle() içinde kontrol edilir)
    açılıp kapanıyor. Kendi _CycleLock'u: TÜM USDT perpetual'ları (300+)
    taramak run_trading_cycle_task'ın 50 sembollük watchlist'inden çok daha
    uzun sürebilir, aynı DOLOUSDT/kuyruk-tıkanması hata sınıfına bir daha
    düşülmesin diye."""
    from services.pump_fade_strategy import PumpFadeStrategy

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    with _CycleLock("lock:run_pump_fade_cycle_task", ttl_seconds=1500) as acquired:
        if not acquired:
            return {"skipped": "previous_cycle_still_running"}
        return PumpFadeStrategy().run_cycle()


@celery_app.task(name="run_pairs_trading_task")
def run_pairs_trading_task() -> dict:
    """Faz 200: pairs trading / istatistiksel arbitraj — gerçek Engle-
    Granger kointegrasyon testi + spread z-score (bkz. analytics/
    pairs_trading.py). Kointegrasyon/z-score yavaş değişen istatistiksel
    ilişkiler olduğu için trading cycle'dan (90sn) daha seyrek çalışıyor."""
    from services.pairs_trader import PairsTrader

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    results = PairsTrader().check_and_trade_pairs()
    return {"pairs": results}


@celery_app.task(name="close_due_positions_task")
def close_due_positions_task() -> dict:
    """Faz 187/188: celery beat tarafından periyodik çalıştırılır (bkz.
    celery_app.py:beat_schedule) — açık pozisyonları gerçek güncel
    fiyatla kontrol edip stop/hedef/likidasyona ulaşanları kapatır. Faz
    265: hold_seconds/trade_horizon parametresi kaldırıldı — Faz 215'ten
    beri PositionCloser bunu zaten hiç kullanmıyordu (vade dolunca zorla
    kapatma yok, sadece gerçekten stop/hedefe ulaşınca).

    Faz 269-sonrası — KRİTİK bulgu, canlıda yakalandı: list_open_positions
    artık limit=None ile TÜM açık pozisyonları tarıyor (bkz. o
    değişikliğin commit'i — önceden en eski binlerce pozisyon hiç
    kontrol edilmiyordu). Ama GERÇEKTEN 2631 pozisyonu (her biri gerçek
    bir Binance/Yahoo fiyat isteği) 60sn'lik beat aralığında bitirmek
    imkansız hale geldi — bu task'ın _CycleLock'u YOKTU (run_trading_
    cycle_task'ın aksine), restart sonrası GERÇEKTEN 9 kopyası aynı anda
    kuyruğa girdiği doğrulandı (aynı pozisyonları eşzamanlı işleyip
    çakışma/gereksiz tekrar isteği riski). run_trading_cycle_task ile
    AYNI Redis SETNX kilidi — önceki çalışma sürerken yenisi sessizce
    atlanır."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from services.position_closer import PositionCloser

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    with _CycleLock("lock:close_due_positions_task", ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": "previous_run_still_in_progress"}

        # Faz 194: açık pozisyonlar artık farklı varlık sınıflarında
        # olabilir (kripto + hisse/endeks/emtia) — RoutingProvider her
        # pozisyonu kendi gerçek fiyat kaynağına yönlendiriyor.
        closer = PositionCloser(RoutingProvider())
        with SessionFactory.get_session() as session:
            closed = closer.close_due_positions(DecisionPersistor(session))

    return {"closed_count": len(closed), "closed": closed}


@celery_app.task(name="close_due_shadow_positions_task")
def close_due_shadow_positions_task() -> dict:
    """Shadow Mode (Faz 268-sonrası) — close_due_positions_task ile AYNI
    cadence'te (bkz. celery_app.py:beat_schedule) macro-only gölge
    pozisyonları gerçek güncel fiyatla kontrol edip stop/hedefe
    ulaşanları kapatır. Gerçek pozisyonları asla etkilemez, ayrı bir
    tablo (shadow_positions) üzerinde çalışır."""
    from services.macro_shadow_tracker import close_due_positions

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    closed = close_due_positions()
    return {"closed_count": len(closed), "closed": closed}


@celery_app.task(name="close_due_benched_shadow_positions_task")
def close_due_benched_shadow_positions_task() -> dict:
    """Faz 316-sonrası — close_due_shadow_positions_task ile AYNI cadence,
    ama "benched ajan itirazı" gölge pozisyonları için (bkz. services/
    benched_agent_shadow_tracker.py). Gerçek pozisyonları asla etkilemez."""
    from services.benched_agent_shadow_tracker import close_due_positions as close_due_benched_positions

    if _real_market_data_source_or_none() is None:
        return {"skipped": "non_binance_market_data_source"}

    closed = close_due_benched_positions()
    return {"closed_count": len(closed), "closed": closed}


@celery_app.task(name="reconcile_execution_state_task")
def reconcile_execution_state_task() -> dict:
    """Faz 315 — Execution Layer, Faz 1: DB'deki execution_mode='testnet'
    açık pozisyonlarını borsadaki GERÇEK durumla karşılaştırır (bkz.
    services/execution_reconciliation.py). close_due_positions_task'ın
    (60sn'de bir) yaptığı kontrolden BAĞIMSIZ, ikinci bir güvenlik ağı —
    o task bir pozisyonu atlarsa/hata verirse burada yakalanır. Hiçbir
    otomatik düzeltme YAPMAZ, sadece işaretler/loglar (plan kararı).
    execution_service henüz yapılandırılmamışsa (testnet anahtarları
    yoksa — bugünkü varsayılan durum) anında no-op döner."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.event_log_repository import EventLogRepository
    from database.session_factory import SessionFactory
    from services.execution_reconciliation import reconcile_execution_state

    with SessionFactory.get_session() as session:
        result = reconcile_execution_state(
            decision_repo=DecisionPersistor(session),
            event_repo=EventLogRepository(session),
        )
    return result


@celery_app.task(name="refresh_meta_learning_effectiveness_report_task")
def refresh_meta_learning_effectiveness_report_task() -> dict:
    """Cognitive Core 2.0 / M10 (Faz 744-768) — kullanıcı onayıyla
    (2026-08-19) 4 Grup B modülünden biri: meta_optimizer/agent_tuner.py'nin
    (CMA-ES) GERÇEK onaylı turlarının zamanla iyileşip iyileşmediğini
    (Spearman trend testi) ölçer. SADECE tespit/rapor — hiçbir tuning
    kararını otomatik onaylamıyor/uygulamıyor."""
    from contracts.meta_learning_effectiveness_report import MetaLearningEffectivenessReport
    from database.repositories.meta_learning_effectiveness_report_repository import (
        MetaLearningEffectivenessReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.meta_learning_effectiveness_gatherer import gather_meta_learning_effectiveness

    result = gather_meta_learning_effectiveness()
    with SessionFactory.get_session() as session:
        report = MetaLearningEffectivenessReport(result=result)
        MetaLearningEffectivenessReportRepository(session).save(report)

    return {"id": str(report.id), "n_approved_rounds": result.get("n_approved_rounds")}


@celery_app.task(name="refresh_market_world_model_report_task")
def refresh_market_world_model_report_task() -> dict:
    """Cognitive Core 5.0-6.0 (Faz 901-940) — kullanıcı onayıyla
    (2026-08-19) 4 Grup B modülünden biri: GERÇEK kapanmış işlem
    getirilerinden Moving Block Bootstrap (Künsch, 1989) ile zaman-serisi
    bağımlılığını koruyan bir kümülatif getiri dağılımı üretir. SADECE
    simülasyon/rapor — hiçbir pozisyon/risk kararını otomatik değiştirmiyor."""
    from contracts.market_world_model_report import MarketWorldModelReport
    from database.repositories.market_world_model_report_repository import (
        MarketWorldModelReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.market_world_model_gatherer import gather_market_world_model

    result = gather_market_world_model()
    with SessionFactory.get_session() as session:
        report = MarketWorldModelReport(result=result)
        MarketWorldModelReportRepository(session).save(report)

    return {"id": str(report.id), "n_returns": result.get("n_returns")}


@celery_app.task(name="refresh_direction_prediction_v2_report_task")
def refresh_direction_prediction_v2_report_task() -> dict:
    """Cognitive Core 2.0 / M4 (Faz 519-543) — kullanıcı onayıyla
    (2026-08-19) 4 Grup B modülünden biri: her ajanın GERÇEK (confidence,
    was_correct) çiftlerinden Brier Score (Brier, 1950) hesaplar — hem
    kalibrasyon hem çözünürlüğü TEK bir sayıda birleştirir. SADECE
    ölçüm/rapor."""
    from contracts.direction_prediction_v2_report import DirectionPredictionV2Report
    from database.repositories.direction_prediction_v2_report_repository import (
        DirectionPredictionV2ReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.direction_prediction_v2_gatherer import gather_direction_prediction_v2

    result = gather_direction_prediction_v2()
    with SessionFactory.get_session() as session:
        report = DirectionPredictionV2Report(result=result)
        DirectionPredictionV2ReportRepository(session).save(report)

    return {"id": str(report.id), "domain_count": len(result.get("by_domain") or {})}


@celery_app.task(name="refresh_opportunity_quality_report_task")
def refresh_opportunity_quality_report_task() -> dict:
    """Cognitive Core 2.0 (Faz 569-593) — kullanıcı onayıyla (2026-08-19)
    4 Grup B modülünden biri: de Prado'nun meta-labeling ilkesiyle,
    GERÇEK kapanmış işlemleri council'in ajan-oyu anlaşma derecesine göre
    gruplayıp win_rate'i karşılaştırır. SADECE ölçüm/rapor — hiçbir
    pozisyon/risk kararını otomatik değiştirmiyor."""
    from contracts.opportunity_quality_report import OpportunityQualityReport
    from database.repositories.opportunity_quality_report_repository import (
        OpportunityQualityReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.opportunity_quality_gatherer import gather_opportunity_quality

    result = gather_opportunity_quality()
    with SessionFactory.get_session() as session:
        report = OpportunityQualityReport(result=result)
        OpportunityQualityReportRepository(session).save(report)

    return {"id": str(report.id), "n_trades": result.get("n_trades")}


@celery_app.task(name="refresh_agent_ablation_report_task")
def refresh_agent_ablation_report_task() -> dict:
    """Faz 296 — kullanıcı isteği (2026-08-19): mevcut auto-bench SADECE
    davranışsal/geriye dönük doğruluk ölçüyordu, "bu ajanın oyu olmasaydı
    gerçekleşen kararlar farklı olur muydu" sorusuna hiç cevap vermiyordu.
    GERÇEK kapanmış kararların saklanmış agent_contributions'ından
    leave-one-out rekonstrüksiyon yapar (services/belief_engine.py::
    synthesize'ı hedef ajan sıfırlanmış halde yeniden çalıştırır). SADECE
    ölçüm/rapor — hiçbir ajanın canlı oy hakkını otomatik değiştirmiyor."""
    from contracts.agent_ablation_report import AgentAblationReport
    from database.repositories.agent_ablation_report_repository import (
        AgentAblationReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.agent_ablation_gatherer import gather_agent_ablation

    result = gather_agent_ablation()
    with SessionFactory.get_session() as session:
        report = AgentAblationReport(result=result)
        AgentAblationReportRepository(session).save(report)

    return {"id": str(report.id), "n_decisions_analyzed": result.get("n_decisions_analyzed")}


@celery_app.task(name="refresh_tp_sl_confluence_report_task")
def refresh_tp_sl_confluence_report_task() -> dict:
    """Faz 299-300 — kullanıcı isteği (2026-08-19): TP/SL Confluence
    "wire edilmiş" (RiskTargetStage artık hedefi gerçek yapısal
    bölgelere göre sıkılaştırıyor). Bu haftalık görev SADECE gözlem/
    izleme — mevcut ATR-tabanlı hedefin watchlist genelinde gerçek
    yapısal desteğe ne sıklıkla denk geldiğini raporlar."""
    from contracts.tp_sl_confluence_report import TpSlConfluenceReport
    from database.repositories.tp_sl_confluence_report_repository import (
        TpSlConfluenceReportRepository,
    )
    from database.session_factory import SessionFactory
    from services.tp_sl_confluence_gatherer import gather_tp_sl_confluence

    result = gather_tp_sl_confluence()
    with SessionFactory.get_session() as session:
        report = TpSlConfluenceReport(result=result)
        TpSlConfluenceReportRepository(session).save(report)

    return {"id": str(report.id), "symbols_analyzed": result.get("symbols_analyzed")}
