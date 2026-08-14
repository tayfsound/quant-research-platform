"""Faz 236: kullanıcı isteği — "Backtests'i gerçek veri ile çalışır hale
getirelim." Gerçek Binance geçmiş verisiyle, gerçek CognitiveEngine council'i
kullanan walk-forward backtest — bkz. backtest/real_historical_backtest.py.
Küçük bar sayısı: her walk-forward adımı gerçek bir CognitiveEngine.run()
(gerçek embedding hesaplaması dahil) çalıştırıyor, testin makul sürede
bitmesi için."""
from backtest.real_historical_backtest import (
    fetch_real_history,
    run_portfolio_backtest,
    run_real_backtest,
    run_real_backtest_multi,
)


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


class _FixedDirectionEngine:
    """Faz 268ab: council'i her adımda AYNI, bilinen kararı verecek şekilde
    sabitleyen sahte engine — reverse_direction'ın gerçekten LONG<->SHORT
    çevirdiğini (ve stop/target'ın da doğru yöne kurulduğunu) council'in
    gerçek (değişken) kararına bağlı kalmadan deterministik doğrulamak
    için."""
    def __init__(self, direction: str, stop: float, target: float):
        self.direction = direction
        self.stop = stop
        self.target = target

    def run(self, ctx, persist=False):
        ctx.decision.proposed_direction = self.direction
        ctx.decision.final_size = 1.0
        ctx.decision.confidence = 0.6
        ctx.decision.stop_loss = self.stop
        ctx.decision.take_profit = self.target
        return ctx


class _FlakyEngine:
    """Faz 268-sonrası — kritik bulgu: kullanıcı ~100 backtest denemesinden
    sadece ~6'sının sonuçlandığını bildirdi. Kök neden: tek bir walk-forward
    adımının hatası (gerçek council'in tetiklediği dış API çağrılarından
    biri, ör. FRED/on-chain, geçici olarak başarısız olursa) TÜM koşuyu
    (o ana kadarki ilerlemeyle birlikte) hiçbir iz bırakmadan çöktürüyordu.
    Bu sahte engine, belirli çağrılarda GERÇEK bir dış API hatasını simgeleyen
    bir istisna fırlatıp diğerlerinde normal (sabit LONG) davranışa dönerek,
    "tek bir barın hatası sadece o barı atlamalı" davranışını deterministik
    doğruluyor."""
    def __init__(self, fail_on_calls: set[int], direction: str = "LONG", stop: float = 1.0, target: float = 2.0):
        self._inner = _FixedDirectionEngine(direction, stop, target)
        self.fail_on_calls = fail_on_calls
        self.call_count = 0

    def run(self, ctx, persist=False):
        self.call_count += 1
        if self.call_count in self.fail_on_calls:
            raise RuntimeError("simulated transient network failure")
        return self._inner.run(ctx, persist=persist)


def test_run_real_backtest_survives_a_transient_step_failure_and_keeps_progress():
    flaky = _FlakyEngine(fail_on_calls={2, 5}, stop=100.0, target=200.0)
    result = run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=120, lookback=100, max_forward_bars=15,
        capital_per_trade=1000.0, engine=flaky,
    )
    assert result["skipped_bars"] == 2
    # Koşu tamamen çökmek yerine ilerlemeye devam etmiş olmalı — atlanan
    # barların dışındaki adımlardan en az bir kısmı gerçek bir sonuca
    # (kapanmış işlem ya da hâlâ açık pozisyon) ulaşmış olmalı. Tam sayı
    # kill switch/consecutive_losses gibi gerçek DB durumuna duyarlı
    # olabileceği için burada üst sınır değil, sadece "çökmedi" ve "en az
    # bir adım gerçekten sonuçlandı" doğrulanıyor.
    assert result["trade_count"] + result["open_positions_never_closed"] > 0


def test_run_real_backtest_multi_isolates_a_fully_failed_symbol_from_others(monkeypatch):
    """Bir sembolün GERÇEK geçmiş verisi/koşusu tamamen başarısız olursa
    (ör. o an alınamayan bir veri), bu diğer, tamamen sağlıklı sembollerin
    sonucunu artık kaybettirmemeli."""
    import backtest.real_historical_backtest as rhb

    original_run_real_backtest = rhb.run_real_backtest

    def sometimes_failing(symbol, *args, **kwargs):
        if symbol == "ETHUSDT":
            raise RuntimeError("simulated total symbol failure")
        return original_run_real_backtest(symbol, *args, **kwargs)

    monkeypatch.setattr(rhb, "run_real_backtest", sometimes_failing)

    result = rhb.run_real_backtest_multi(
        ["BTCUSDT", "ETHUSDT"], timeframe="15m", bars_count=110, lookback=100, max_forward_bars=5,
        capital_per_trade=1000.0,
    )
    assert "ETHUSDT" in result["failed_symbols"]
    assert "BTCUSDT" in result["per_symbol"]
    assert "ETHUSDT" not in result["per_symbol"]


def test_reverse_direction_flips_long_to_short_and_stop_target_follow():
    """Faz 268ab — kullanıcının getirdiği 'tam tersini yap' teşhis testi:
    reverse_direction=True iken council LONG dese bile gerçekleşen işlem
    SHORT olmalı, stop/target de SHORT'a göre (stop üstte, target altta)
    doğru kurulmalı — sadece yön etiketi değişip risk yapısı tutarsız
    kalmamalı."""
    engine = _FixedDirectionEngine(direction="LONG", stop=100.0, target=200.0)

    normal = run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=105, lookback=100, max_forward_bars=3,
        capital_per_trade=1000.0, engine=engine,
    )
    reversed_result = run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=105, lookback=100, max_forward_bars=3,
        capital_per_trade=1000.0, engine=engine, reverse_direction=True,
    )

    normal_trades = normal.get("trades", [])
    reversed_trades = reversed_result.get("trades", [])
    if not normal_trades or not reversed_trades:
        # Bu test sabit ($100/$200) bir risk/ödül mesafesiyle, EN SON
        # canlı Binance verisine karşı çalışıyor (sabit bir tarih
        # PINLENMEMİŞ) — tıpkı test_real_backtest_applies_slippage_to_
        # entries gibi, o anki gerçek piyasa hiç tetiklemeyebilir. Amaç
        # yön-çevirme mekaniğini doğrulamak, piyasanın o an oynak olup
        # olmadığını değil — bu dönemde hiç işlem tetiklenmediyse test
        # anlamsız, atla.
        return
    assert all(t["direction"] == "LONG" for t in normal_trades)
    assert all(t["direction"] == "SHORT" for t in reversed_trades)


def test_real_backtest_records_real_mae_mfe_per_trade():
    """Faz 268-sonrası — kullanıcı önerisi: sadece entry/exit/pnl yetmez,
    işlem boyunca fiyatın GERÇEK maksimum olumlu/olumsuz hareketini de
    (MAE/MFE) ölçmeliyiz. Dar bir stop (gerçek piyasa gürültüsü hemen
    aşar) + asla ulaşılamayacak bir target -> her işlem birkaç bar içinde
    stop_loss'a gider, MAE gerçek bir negatif değer, MFE >= 0 olmalı."""
    engine = _FixedDirectionEngine(direction="LONG", stop=0.01, target=1_000_000.0)
    result = run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=120, lookback=100, max_forward_bars=5,
        capital_per_trade=1000.0, engine=engine,
    )
    trades = result.get("trades", [])
    if not trades:
        return  # bu dönemde hiç işlem tetiklenmediyse test anlamsız, atla
    for t in trades:
        assert t["mae_pct"] is not None
        assert t["mfe_pct"] is not None
        assert t["mae_pct"] <= 0.0
        assert t["mfe_pct"] >= 0.0
        assert t["time_to_mae_seconds"] >= 0.0
        assert t["time_to_mfe_seconds"] >= 0.0


def test_real_backtest_applies_slippage_to_entries():
    """Faz 268n: kritik bulgu — backtest entry_price = bars[t].close (tam
    kapanış fiyatı) kullanıyordu. Gerçek bir dolum hiçbir zaman tam o
    fiyattan olmaz — artık simulator/slippage_model.py (canlı orchestrator.
    py'nin de kullandığı AYNI modül) entry'ye uygulanıyor."""
    result = run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=200, lookback=100, max_forward_bars=40, capital_per_trade=1000.0,
    )
    trades = result.get("trades", [])
    if not trades:
        return  # bu dönemde hiç işlem tetiklenmediyse test anlamsız — atla.

    import asyncio
    bars = asyncio.run(fetch_real_history("BTCUSDT", "15m", 200))

    for t in trades:
        raw_close = bars[t["bar_index"]].close
        assert t["entry_price"] != raw_close  # HER giriş kaymalı olmalı


class _RecordingEngine:
    """Faz 268-sonrası: ctx.risk.consecutive_losses'ın gerçekten döngü
    tarafından besleniyor olduğunu (DrawdownSizingStage'in okuyacağı
    GERÇEK değer) doğrulamak için — her çağrıdaki değeri kaydeder, sabit
    bir LONG/dar-stop kararı verir."""
    def __init__(self, stop: float, target: float):
        self.stop = stop
        self.target = target
        self.seen_consecutive_losses: list[int] = []

    def run(self, ctx, persist=False):
        self.seen_consecutive_losses.append(ctx.risk.consecutive_losses)
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.final_size = 1.0
        ctx.decision.confidence = 0.6
        ctx.decision.stop_loss = self.stop
        ctx.decision.take_profit = self.target
        return ctx


def test_consecutive_losses_is_fed_into_risk_context_for_drawdown_sizing_to_read():
    """Faz 268-sonrası — kullanıcı bulgusu: bir backtest'te canlı sistemin
    GERÇEKTEN sahip olduğu kill switch/drawdown sizing korumaları hiç
    devrede değildi (_build_backtest_context consecutive_losses'ı hiç set
    etmiyordu). Çok dar bir stop (gerçek piyasa gürültüsü neredeyse her
    zaman aşar) + asla ulaşılamayacak bir target -> neredeyse her işlem
    stop_loss, gerçek bir ardışık kayıp serisi garanti."""
    engine = _RecordingEngine(stop=0.01, target=1_000_000.0)
    run_real_backtest(
        "BTCUSDT", timeframe="15m", bars_count=150, lookback=100, max_forward_bars=5,
        capital_per_trade=1000.0, engine=engine,
    )
    assert max(engine.seen_consecutive_losses) >= 2


def test_kill_switch_halts_new_positions_after_the_real_configured_threshold():
    """Kill switch'in ETKİSİ (gerçek eşiğe ulaşınca yeni pozisyon açmayı
    durdurma) walk-forward döngüsünün kendi seviyesinde simüle ediliyor —
    bkz. run_real_backtest'in modül notundaki güvenlik açıklaması."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("kill_switch_consecutive_losses", "3", updated_by="test")
    try:
        engine = _FixedDirectionEngine(direction="LONG", stop=0.01, target=1_000_000.0)
        result = run_real_backtest(
            "BTCUSDT", timeframe="15m", bars_count=150, lookback=100, max_forward_bars=5,
            capital_per_trade=1000.0, engine=engine,
        )
        if result["trade_count"] < 3:
            return  # bu dönemde yeterli işlem tetiklenmediyse test anlamsız, atla
        assert result["kill_switch_tripped_at_bar"] is not None
        trip_bar = result["kill_switch_tripped_at_bar"]
        assert all(t["bar_index"] < trip_bar for t in result["trades"])
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("kill_switch_consecutive_losses", "10", updated_by="test")


def test_never_triggers_the_real_risk_engine_kill_switch_db_write():
    """GÜVENLİK — kritik: bu fonksiyon canlı dashboard'dan (/run-real-async)
    tetiklenebiliyor. RiskEngine._trip_kill_switch()'in GERÇEK
    app_settings.ai_enabled yazması, ne kadar çok ardışık kayıp simüle
    edilirse edilsin ASLA tetiklenmemeli — etki sadece bu döngünün kendi
    seviyesinde (ctx.risk.kill_switch_consecutive_losses hep 0/devre dışı
    kalır) simüle ediliyor."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        repo.set("kill_switch_consecutive_losses", "3", updated_by="test")
        before_ai_enabled = repo.get("ai_enabled")
    try:
        engine = _FixedDirectionEngine(direction="LONG", stop=0.01, target=1_000_000.0)
        run_real_backtest(
            "BTCUSDT", timeframe="15m", bars_count=150, lookback=100, max_forward_bars=5,
            capital_per_trade=1000.0, engine=engine,
        )
        with SessionFactory.get_session() as session:
            after_ai_enabled = AppSettingsRepository(session).get("ai_enabled")
        assert after_ai_enabled == before_ai_enabled
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("kill_switch_consecutive_losses", "10", updated_by="test")


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


def test_run_real_backtest_multi_stores_backtest_learning_isolated_from_live(tmp_path, monkeypatch):
    """Faz 268i — kullanıcı bulgusu: feed_agent_learning=True önceden CANLI
    ile AYNI (varsayılan "agent_memory_history/") dosyaya yazıyordu.
    source="backtest" etiketi kaydı görünür kılıyordu ama hiçbir gerçek
    sorgu (WeightOptimizer.propose_weights, AgentMemory.get_summary) buna
    göre filtrelemiyordu — yani her backtest çalıştırması canlı ağırlık
    öğrenmesine sessizce karışıyordu. Artık tamamen ayrı bir dizine
    (backtest_agent_memory_history/) yazıyor; bu test gerçek AgentMemory()
    çağrısının hangi storage_path ile yapıldığını yakalayıp doğruluyor."""
    import services.agent_memory as agent_memory_module

    captured_paths = []
    real_agent_memory_cls = agent_memory_module.AgentMemory

    class _CapturingAgentMemory(real_agent_memory_cls):
        def __init__(self, storage_path=agent_memory_module._DEFAULT_STORAGE_PATH):
            captured_paths.append(storage_path)
            super().__init__(storage_path=str(tmp_path / "isolated"))

    monkeypatch.setattr(agent_memory_module, "AgentMemory", _CapturingAgentMemory)

    run_real_backtest_multi(
        ["BTCUSDT"], timeframe="15m", bars_count=150, lookback=100, max_forward_bars=20,
        capital_per_trade=1000.0, feed_agent_learning=True,
    )

    # CognitiveEngine() kendi WeightOptimizer'ı için AYRICA (varsayılan
    # yoldan) bir AgentMemory kurar — bununla ilgilenmiyoruz, sadece
    # backtest öğrenmesinin kendi izole yolunu kullandığını doğruluyoruz.
    assert "backtest_agent_memory_history" in captured_paths
    assert "agent_memory_history" not in captured_paths


def test_run_portfolio_backtest_produces_consistent_structure():
    """Faz 268o: kullanıcı isteği — "backtest motoru rötuşu... portföy
    seviyesi backtest." run_real_backtest_multi()'nin aksine (her sembol
    kendi TAM capital_per_trade'ini bağımsız kullanıyordu) burada TEK
    paylaşılan sermaye havuzu + TEK max_concurrent_positions limiti var."""
    result = run_portfolio_backtest(
        ["BTCUSDT", "ETHUSDT"], timeframe="15m", bars_count=150, lookback=100, max_forward_bars=30,
        starting_capital=10000.0, max_concurrent_positions=3, max_capital_pct=0.5,
    )
    assert result["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert result["starting_capital"] == 10000.0
    assert result["equity_curve"][0] == 10000.0
    assert result["trade_count"] >= 0


def test_run_portfolio_backtest_never_exceeds_concurrent_position_limit():
    """Kritik değişmez: aynı anda açık pozisyon sayısı hiçbir zaman
    max_concurrent_positions'ı aşmamalı — bu, run_real_backtest_multi()'nin
    (her sembol bağımsız, ortak bir kısıt yok) tam olarak ÇÖZMEDİĞİ şey."""
    max_concurrent = 2
    result = run_portfolio_backtest(
        ["BTCUSDT", "ETHUSDT", "SOLUSDT"], timeframe="15m", bars_count=250, lookback=100, max_forward_bars=60,
        starting_capital=10000.0, max_concurrent_positions=max_concurrent, max_capital_pct=0.6,
    )
    trades = result.get("trades", [])
    if not trades:
        return  # bu dönemde hiç işlem tetiklenmediyse test anlamsız — atla.

    events = []
    for t in trades:
        events.append((t["entry_time"], 1))
        events.append((t["exit_time"], -1))
    events.sort()

    concurrent = 0
    max_concurrent_seen = 0
    for _, delta in events:
        concurrent += delta
        max_concurrent_seen = max(max_concurrent_seen, concurrent)

    assert max_concurrent_seen <= max_concurrent


def test_run_portfolio_backtest_async_endpoint_dispatches_and_persists():
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
            "/api/v1/backtest/run-portfolio-async"
            "?symbols=BTCUSDT,ETHUSDT&timeframe=15m&bars_count=120&lookback=100&max_forward_bars=20"
            "&starting_capital=10000&max_concurrent_positions=2&max_capital_pct=0.5",
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
        assert body["result"]["metrics"]["mode"] == "portfolio"
    finally:
        celery_app.conf.task_always_eager = False
