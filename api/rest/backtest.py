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
def run_backtest(
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
def run_backtest_async(
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
def run_real_backtest_async(
    symbols: str = "BTCUSDT",
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = 100,
    max_forward_bars: int | None = None,
    capital_per_trade: float = 1000.0,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
    getirelim." /run'ın aksine (deterministik, sahte MockOHLCVAdapter
    fiyatları) burası GERÇEK Binance geçmiş verisiyle, gerçek 9-ajan
    council'i kullanarak walk-forward çalışıyor — bkz. backtest/
    real_historical_backtest.py. Her adım gerçek bir CognitiveEngine.run()
    çalıştırdığı için dakikalar sürebilir, bu yüzden her zaman async
    (celery) — senkron bir "/run-real" kasıtlı olarak yok.

    max_forward_bars=None (varsayılan) ise zaman dilimine göre GERÇEK
    süreyi sabit tutacak şekilde otomatik ölçeklenir (bkz. backtest/
    real_historical_backtest.py::_default_max_forward_bars) — 200'lük
    eski sabit sadece 1h/4h/1d'de yeterliydi, 5m/15m'de hiçbir kararın
    kapanma şansı bulamamasına yol açıyordu (kullanıcı bulgusu)."""
    from services.tasks import run_real_backtest_task

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    task = run_real_backtest_task.delay(
        symbol_list, timeframe, bars_count, lookback, max_forward_bars, capital_per_trade
    )
    return {"task_id": task.id, "status": "queued"}


@router.post("/run-portfolio-async")
def run_portfolio_backtest_async(
    symbols: str = "BTCUSDT,ETHUSDT",
    timeframe: str = "15m",
    bars_count: int = 1000,
    lookback: int = 100,
    max_forward_bars: int | None = None,
    starting_capital: float = 10000.0,
    max_concurrent_positions: int = 5,
    max_capital_pct: float = 0.5,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    """Faz 268o: kullanıcı isteği — "backtest motoru rötuşu... portföy
    seviyesi backtest." /run-real-async'ten (her sembol KENDİ TAM
    sermayesini bağımsız kullanır, ortak bir kısıt yok) farkı: burada TÜM
    semboller TEK bir paylaşılan sermaye havuzunu ve TEK bir
    max_concurrent_positions limitini paylaşarak GERÇEKTEN aynı anda
    simüle edilir — bkz. backtest/real_historical_backtest.py::
    run_portfolio_backtest. Aynı sebeple (her adım gerçek bir Cognitive
    Engine.run()) her zaman async."""
    from services.tasks import run_portfolio_backtest_task

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    task = run_portfolio_backtest_task.delay(
        symbol_list, timeframe, bars_count, lookback, max_forward_bars,
        starting_capital, max_concurrent_positions, max_capital_pct,
    )
    return {"task_id": task.id, "status": "queued"}


@router.get("/tasks/{task_id}")
def get_backtest_task(task_id: str, user: AuthContext = Depends(get_current_user)):
    from services.celery_app import celery_app
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)
    body = {"task_id": task_id, "status": result.status}
    if result.successful():
        body["result"] = result.result
    elif result.failed():
        body["error"] = str(result.result)
    return body


@router.get("/active")
def active_backtest_tasks(user: AuthContext = Depends(get_current_user)):
    """Faz 268c — kullanıcı bulgusu: "arka planda hali hazırda çalışan
    bir test olduğunda ben bunu göremiyorum." Önceki çözüm (dashboard'da
    task_id'yi localStorage'a yazmak) sadece AYNI tarayıcıda, task'ı
    BAŞLATAN kişi için işe yarıyordu — farklı bir sekme/cihaz/kullanıcı
    hâlâ hiçbir şey göremiyordu. Bu, celery worker'a GERÇEKTEN sorup o an
    aktif olan backtest task'larını döndürüyor — kim/nereden başlattığından
    bağımsız, her zaman doğru (task_id hatırlamaya gerek yok)."""
    from services.celery_app import celery_app

    backtest_task_names = {
        "run_backtest_task", "run_real_backtest_task", "run_portfolio_backtest_task",
    }
    try:
        inspector = celery_app.control.inspect(timeout=2.0)
        active = inspector.active() or {}
    except Exception:
        # Worker'a ulaşılamıyorsa (ör. Redis geçici olarak erişilemez):
        # fail-closed — "kesinlikle boş" ile "sorgulanamadı"yı UI'ın
        # karıştırmaması için ayrı bir alanla işaretleniyor.
        return {"active": [], "inspection_available": False}

    tasks = []
    for worker, task_list in active.items():
        for t in task_list or []:
            if t.get("name") in backtest_task_names:
                tasks.append({
                    "task_id": t.get("id"),
                    "name": t.get("name"),
                    "args": t.get("args"),
                    "worker": worker,
                    "time_start": t.get("time_start"),
                })
    return {"active": tasks, "inspection_available": True}


@router.get("/runs")
def list_runs(limit: int = 20, user: AuthContext = Depends(get_current_user)):
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
