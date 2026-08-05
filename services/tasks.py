"""Sprint 27: Celery tasks for heavy, request-response-unfriendly work."""
from services.celery_app import celery_app


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
    from market_data.ingestion.data_provider import get_ohlcv_provider
    from services.position_closer import PositionCloser

    if hold_seconds is None:
        with SessionFactory.get_session() as session:
            horizon = AppSettingsRepository(session).get("trade_horizon")
        hold_seconds = TRADE_HORIZON_SECONDS.get(horizon, 600)

    closer = PositionCloser(get_ohlcv_provider(), hold_seconds=hold_seconds)
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
