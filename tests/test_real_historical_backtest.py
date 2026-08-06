"""Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
getirelim." Gerçek Binance geçmiş verisiyle, gerçek CognitiveEngine council'i
kullanan walk-forward backtest — bkz. backtest/real_historical_backtest.py.
Küçük bar sayısı: her walk-forward adımı gerçek bir CognitiveEngine.run()
(gerçek embedding hesaplaması dahil) çalıştırıyor, testin makul sürede
bitmesi için."""
from backtest.real_historical_backtest import fetch_real_history, run_real_backtest


def test_fetch_real_history_returns_real_binance_bars():
    import asyncio
    bars = asyncio.run(fetch_real_history("BTCUSDT", "15m", 50))
    assert len(bars) == 50
    assert all(b.close > 0 for b in bars)
    assert bars[0].timestamp < bars[-1].timestamp


def test_run_real_backtest_async_endpoint_dispatches_and_persists():
    """Faz 236: POST /backtest/run-real-async — gerçek veri backtest'i her
    zaman async (celery), çünkü her adım gerçek bir CognitiveEngine.run()
    (gerçek embedding hesaplaması dahil) çalıştırıyor. NOT: burada
    transformers.* mock'lanMIYOR (diğer celery task testlerinin aksine) —
    çünkü bu backtest ctx.market.features'ı GERÇEKTEN dolduruyor (mock
    backtest runner'ın aksine), bu da embedding tabanlı SemanticSearch
    yolunu tetikliyor; o yol standart transformers mock deseniyle çalışmıyor
    (bkz. backtest/cognitive_backtest_runner.py'nin kendi notu)."""
    from fastapi.testclient import TestClient
    from api.main import app
    from services.celery_app import celery_app
    from contracts.auth import Role
    from tests.auth_helpers import make_authed_headers

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        client = TestClient(app)
        dispatch = client.post(
            "/api/v1/backtest/run-real-async"
            "?symbols=BTCUSDT&timeframe=15m&bars_count=120&lookback=100&max_forward_bars=20",
            headers=make_authed_headers(Role.OPERATOR),
        )
        assert dispatch.status_code == 200
        task_id = dispatch.json()["task_id"]

        status = client.get(
            f"/api/v1/backtest/tasks/{task_id}", headers=make_authed_headers(Role.VIEWER)
        )
        assert status.status_code == 200
        body = status.json()
        assert body["status"] == "SUCCESS"
        assert "id" in body["result"]
        assert body["result"]["metrics"]["mode"] == "real_historical"
    finally:
        celery_app.conf.task_always_eager = False


def test_run_real_backtest_produces_real_consistent_metrics():
    result = run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=120, lookback=100, max_forward_bars=20, capital_per_trade=1000.0,
    )
    assert result["symbol"] == "BTCUSDT"
    assert result["num_bars"] == 120
    assert result["trade_count"] >= 0

    if result["trade_count"] > 0:
        m = result["metrics"]
        assert 0.0 <= m["win_rate"] <= 1.0
        assert isinstance(m["sharpe_ratio"], float)
        assert m["exit_reason_distribution"].keys() <= {"stop_loss", "take_profit"}
        # equity curve gerçek $ kümülatif pnl'i takip etmeli.
        assert len(result["equity_curve"]) == result["trade_count"] + 1
        assert result["equity_curve"][0] == 1000.0
        assert abs(result["equity_curve"][-1] - (1000.0 + result["total_pnl_usd"])) < 0.01
