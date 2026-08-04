"""Sprint 27: Celery tasks for heavy, request-response-unfriendly work."""
from services.celery_app import celery_app


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
