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
    from market_data.ingestion.data_provider import get_provider_for_symbol
    from services.orchestrator import CognitiveOrchestrator

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        ai_enabled = settings_repo.get("ai_enabled") == "true"
        watchlist = [s.strip() for s in settings_repo.get("watchlist").split(",") if s.strip()]

    if not ai_enabled:
        return {"skipped": "ai_disabled"}

    symbols = [symbol] if symbol else watchlist
    results = []
    for sym in symbols:
        orch = CognitiveOrchestrator(data_provider=get_provider_for_symbol(sym))
        result = orch.run_cycle(symbol=sym)
        results.append({
            "symbol": result.get("symbol"),
            "direction": result.get("direction"),
            "risk_verdict": result.get("risk_verdict"),
            "risk_reasons": result.get("risk_reasons"),
        })

    return results[0] if symbol else {"cycles": results}


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
