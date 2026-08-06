"""Backtest API — Sprint 6, async dispatch added Sprint 27."""
from fastapi import APIRouter, Depends

from backtest.backtest_orchestrator import run_and_persist_backtest
from contracts.auth import Role
from database.repositories.backtest_run_repository import BacktestRunRepository
from database.session_factory import SessionFactory
from market_data.ingestion.mock_adapter import MockOHLCVAdapter
from services.auth_service import AuthContext, get_current_user, require_role

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run")
async def run_backtest(
    symbols: str = "BTCUSDT",
    bars: int = 200,
    seed: int = 42,
    fee: float = 0.001,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Runs a real CognitiveEngine-backed backtest against deterministic mock
    OHLCV data and persists the result. Real historical data ingestion isn't
    wired up yet (see AI_MEMORY_SYSTEM/CURRENT_STATE.md) — this is enough to
    prove the pipeline (engine -> vectorized backtest -> metrics -> persist)
    end to end and reproducibly."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    data = {sym: MockOHLCVAdapter(seed=seed, base_price=100.0).generate(bars) for sym in symbol_list}

    with SessionFactory.get_session() as session:
        run = run_and_persist_backtest(data, session, fee=fee)
        return {
            "id": str(run.id),
            "symbols": run.symbols,
            "num_bars": run.num_bars,
            "total_pnl": run.total_pnl,
            "metrics": run.metrics,
        }


@router.post("/run-async")
async def run_backtest_async(
    symbols: str = "BTCUSDT",
    bars: int = 200,
    seed: int = 42,
    fee: float = 0.001,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Sprint 27: dispatches the same backtest to a Celery worker instead of
    running it inline — for a real historical run (thousands of bars, many
    symbols) this is the "ağır işlem" the roadmap wants off the request
    thread. Returns immediately with a task id."""
    from services.tasks import run_backtest_task

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    task = run_backtest_task.delay(symbol_list, bars, seed, fee)
    return {"task_id": task.id, "status": "queued"}


@router.post("/run-real-async")
async def run_real_backtest_async(
    symbols: str = "BTCUSDT",
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = 100,
    max_forward_bars: int = 200,
    capital_per_trade: float = 1000.0,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
    getirelim." /run'ın aksine (deterministik, sahte MockOHLCVAdapter
    fiyatları) burası GERÇEK Binance geçmiş verisiyle, gerçek 9-ajan
    council'i kullanarak walk-forward çalışıyor — bkz. backtest/
    real_historical_backtest.py. Her adım gerçek bir CognitiveEngine.run()
    çalıştırdığı için dakikalar sürebilir, bu yüzden her zaman async
    (celery) — senkron bir "/run-real" kasıtlı olarak yok."""
    from services.tasks import run_real_backtest_task

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    task = run_real_backtest_task.delay(
        symbol_list, timeframe, bars_count, lookback, max_forward_bars, capital_per_trade
    )
    return {"task_id": task.id, "status": "queued"}


@router.get("/tasks/{task_id}")
async def get_backtest_task(task_id: str, user: AuthContext = Depends(get_current_user)):
    from services.celery_app import celery_app
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)
    body = {"task_id": task_id, "status": result.status}
    if result.successful():
        body["result"] = result.result
    elif result.failed():
        body["error"] = str(result.result)
    return body


@router.get("/runs")
async def list_runs(limit: int = 20, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        rows = BacktestRunRepository(session).list_recent(limit=limit)
        return {
            "runs": [
                {
                    "id": str(r.id),
                    "created_at": r.created_at.isoformat(),
                    "symbols": r.symbols,
                    "total_pnl": r.total_pnl,
                    "metrics": r.metrics,
                }
                for r in rows
            ]
        }
