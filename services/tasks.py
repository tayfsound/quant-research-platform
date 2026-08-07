"""Sprint 27: Celery tasks for heavy, request-response-unfriendly work."""
from services.celery_app import celery_app


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
    open_symbols = [s for s in watchlist if is_market_open(s)]
    closed_symbols = [s for s in watchlist if s not in open_symbols]

    orch = CognitiveOrchestrator(data_provider=RoutingProvider())
    cycles = orch.run_portfolio_aware_cycle(open_symbols) if open_symbols else []
    cycles += [{"symbol": s, "skipped": "market_closed"} for s in closed_symbols]

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


@celery_app.task(name="run_pairs_trading_task")
def run_pairs_trading_task() -> dict:
    """Faz 200: pairs trading / istatistiksel arbitraj — gerçek Engle-
    Granger kointegrasyon testi + spread z-score (bkz. analytics/
    pairs_trading.py). Kointegrasyon/z-score yavaş değişen istatistiksel
    ilişkiler olduğu için trading cycle'dan (90sn) daha seyrek çalışıyor."""
    from services.pairs_trader import PairsTrader

    results = PairsTrader().check_and_trade_pairs()
    return {"pairs": results}


@celery_app.task(name="close_due_positions_task")
def close_due_positions_task(hold_seconds: int | None = None) -> dict:
    """Faz 187/188: celery beat tarafından periyodik çalıştırılır (bkz.
    celery_app.py:beat_schedule) — açık pozisyonlardan kullanıcının
    app_settings'te seçtiği vadeden (trade_horizon) fazla süredir açık
    olanları gerçek güncel fiyatla kapatır."""
    from database.repositories.app_settings_repository import (
        TRADE_HORIZON_SECONDS,
        AppSettingsRepository,
    )
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from services.position_closer import PositionCloser

    if hold_seconds is None:
        with SessionFactory.get_session() as session:
            horizon = AppSettingsRepository(session).get("trade_horizon")
        hold_seconds = TRADE_HORIZON_SECONDS.get(horizon, 600)

    # Faz 194: açık pozisyonlar artık farklı varlık sınıflarında olabilir
    # (kripto + hisse/endeks/emtia) — RoutingProvider her pozisyonu kendi
    # gerçek fiyat kaynağına yönlendiriyor.
    closer = PositionCloser(RoutingProvider(), hold_seconds=hold_seconds)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    return {"closed_count": len(closed), "closed": closed}


@celery_app.task(name="run_backtest_task", bind=True)
def run_backtest_task(self, symbols: list[str], bars: int = 200, seed: int = 42, fee: float = 0.001) -> dict:
    """Runs the same real CognitiveEngine-backed backtest pipeline
    (Sprint 3-6) as POST /backtest/run, but off the request thread — a real
    backtest over a meaningful history is exactly the kind of "ağır işlem"
    (heavy operation) the roadmap says shouldn't block an HTTP response."""
    from database.session_factory import SessionFactory
    from market_data.ingestion.mock_adapter import MockOHLCVAdapter
    from backtest.backtest_orchestrator import run_and_persist_backtest

    data = {
        sym: MockOHLCVAdapter(seed=seed + i, base_price=100.0).generate(bars)
        for i, sym in enumerate(symbols)
    }

    with SessionFactory.get_session() as session:
        run = run_and_persist_backtest(data, session, fee=fee)

    return {
        "id": str(run.id),
        "symbols": run.symbols,
        "total_pnl": run.total_pnl,
        "metrics": run.metrics,
    }


@celery_app.task(name="run_real_backtest_task", bind=True)
def run_real_backtest_task(
    self,
    symbols: list[str],
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = 100,
    max_forward_bars: int = 200,
    capital_per_trade: float = 1000.0,
) -> dict:
    """Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır
    hale getirelim." Her walk-forward adımı gerçek bir CognitiveEngine.run()
    (embedding hesaplaması dahil) çalıştırdığı için 1000 bar'lık bir run
    dakikalar sürebilir — bu yüzden run_backtest_task'ın (mock veri) aynı
    async-dispatch deseni burada da kritik, senkron bir HTTP isteği bunu
    asla karşılayamaz."""
    from database.session_factory import SessionFactory
    from backtest.real_historical_backtest import persist_real_backtest_run, run_real_backtest_multi

    # Faz 248: kullanıcı isteği — backtest sonuçları artık gerçekten
    # AgentMemory'ye (source="backtest" etiketiyle) besleniyor; dashboard'un
    # "Gerçek Veriyle Çalıştır" butonuyla tetiklenen HER gerçek backtest
    # koşusu artık ajan öğrenmesine katkı sağlıyor.
    result = run_real_backtest_multi(
        symbols, timeframe=timeframe, bars_count=bars_count, lookback=lookback,
        max_forward_bars=max_forward_bars, capital_per_trade=capital_per_trade,
        feed_agent_learning=True,
    )

    with SessionFactory.get_session() as session:
        run = persist_real_backtest_run(result, session, lookback=lookback)

    return {
        "id": str(run.id),
        "symbols": run.symbols,
        "total_pnl": run.total_pnl,
        "metrics": run.metrics,
    }
