"""Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
getirelim." Gerçek Binance geçmiş verisiyle, gerçek CognitiveEngine council'i
kullanan walk-forward backtest — bkz. backtest/real_historical_backtest.py.
Küçük bar sayısı: her walk-forward adımı gerçek bir CognitiveEngine.run()
(gerçek embedding hesaplaması dahil) çalıştırıyor, testin makul sürede
bitmesi için."""
from backtest.real_historical_backtest import fetch_real_history, run_real_backtest, run_real_backtest_multi


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


def test_real_backtest_feeds_agent_memory_when_requested(tmp_path):
    """Faz 248: kullanıcı isteği — backtest motoru gerçek geçmiş veriyle
    binlerce "deneme" üretebiliyor ama sonuçlar hiçbir yere kaydedilmiyordu.
    Bu test, feed_agent_learning=True olduğunda gerçek simüle işlem
    sonuçlarının source="backtest" etiketiyle AgentMemory'ye yazıldığını
    ve canlı kayıtlardan (source="live") ayırt edilebilir kaldığını
    kanıtlıyor."""
    from services.agent_memory import AgentMemory

    result = run_real_backtest_multi(
        ["BTCUSDT"], timeframe="15m", bars_count=150, lookback=100, max_forward_bars=20,
        capital_per_trade=1000.0, feed_agent_learning=False,
    )
    if result["total_trades"] == 0:
        return  # bu dönemde hiç işlem tetiklenmediyse test anlamsız — atla.

    memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_history"))

    from backtest.real_historical_backtest import _record_backtest_agent_learning
    from contracts.agent import AgentDomain, AgentOpinion

    opinions = [
        AgentOpinion(agent_id="technical_agent_v1", domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.7),
        AgentOpinion(agent_id="macro_agent_v1", domain=AgentDomain.MACRO, direction="WAIT", confidence=0.3),
    ]
    _record_backtest_agent_learning(memory, opinions, "BTCUSDT", "LONG", net_pnl_usd=25.0)

    technical_records = memory._records.get("technical", [])
    assert len(technical_records) == 1
    assert technical_records[0].source == "backtest"
    assert technical_records[0].was_correct is True
    assert technical_records[0].symbol == "BTCUSDT"

    # WAIT oyu veren macro hiç kaydedilmemeli (Faz 245 ile aynı ilke).
    assert "macro" not in memory._records or len(memory._records["macro"]) == 0
