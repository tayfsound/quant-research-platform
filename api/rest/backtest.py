"""Backtest API — Sprint 6."""
from fastapi import APIRouter

from backtest.backtest_orchestrator import run_and_persist_backtest
from database.repositories.backtest_run_repository import BacktestRunRepository
from database.session_factory import SessionFactory
from market_data.ingestion.mock_adapter import MockOHLCVAdapter

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run")
async def run_backtest(symbols: str = "BTCUSDT", bars: int = 200, seed: int = 42, fee: float = 0.001):
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


@router.get("/runs")
async def list_runs(limit: int = 20):
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
