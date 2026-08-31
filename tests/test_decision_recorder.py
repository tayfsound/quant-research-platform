"""Decision Recorder compatibility tests."""
from datetime import UTC, datetime, timedelta

from contracts.context import CognitiveCycleContext
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor
from services.decision_recorder import DecisionRecorder


def test_record_computes_real_decision_latency_from_last_bar_timestamp():
    """Faz 268-sonrası — kritik bulgu: decision_latency_ms hiç
    doldurulmuyordu (her zaman 0.0 varsayılan). Artık ctx.market.
    raw_snapshot'taki GERÇEK last_bar_timestamp ile ctx.timestamp
    arasındaki farktan hesaplanıyor."""
    recorder = DecisionRecorder()
    now = datetime.now(UTC)
    last_bar = now - timedelta(seconds=45)

    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "raw_snapshot": {"last_bar_timestamp": last_bar.isoformat()}},
        decision={"proposed_size": 0.5},
    )
    ctx.timestamp = now

    event = recorder.record(ctx, [])
    assert 44000 <= event.decision_latency_ms <= 46000


def test_record_defaults_decision_latency_to_zero_without_last_bar_timestamp():
    recorder = DecisionRecorder()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )
    event = recorder.record(ctx, [])
    assert event.decision_latency_ms == 0.0


def test_leverage_is_clamped_to_keep_liquidation_safely_beyond_the_stop(tmp_path):
    """Faz 268-sonrası — gerçek olay (DOLOUSDT): stop mesafesi ~%20 iken
    symbol_leverage'daki 5x hiç sorgulanmadan uygulanıyordu — likidasyon
    fiyatı stop'tan ÖNCE geliyordu, pozisyon planlanan stop'u hiç
    görmeden teminatın neredeyse tamamını kaybediyordu. Artık kaldıraç,
    max_safe_leverage(stop_distance_pct)'e göre otomatik kırpılıyor."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory
    from simulator.margin import max_safe_leverage

    symbol = "DOLOTESTUSDT"
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        original = repo.get("symbol_leverage")
        import json
        mapping = json.loads(original)
        mapping[symbol] = 5
        repo.set("symbol_leverage", json.dumps(mapping), updated_by="test")

    try:
        recorder = DecisionRecorder()
        entry_price = 0.0271
        stop_loss_pct = 0.20  # DOLOUSDT'deki gerçek mesafeyle aynı büyüklükte
        risk_mag = entry_price * stop_loss_pct

        ctx = CognitiveCycleContext(
            market={"symbol": symbol, "raw_snapshot": {"close": entry_price}},
            decision={
                "proposed_direction": "LONG", "final_action": "LONG",
                "final_size": 100.0, "stop_loss_distance": risk_mag, "take_profit_distance": risk_mag * 0.56,
            },
            risk={"evaluation": {"verdict": "approved"}},
        )

        event = recorder.record(ctx, [])

        expected_safe_leverage = max_safe_leverage(stop_loss_pct)
        assert event.leverage < 5.0
        assert event.leverage == round(expected_safe_leverage, 10) or abs(event.leverage - expected_safe_leverage) < 1e-6

        # Kritik doğrulama: likidasyon fiyatı artık stop'tan ÖNCE gelmiyor.
        assert event.liquidation_price < event.stop_loss_price
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("symbol_leverage", original, updated_by="test")


def test_leverage_is_dampened_when_stacking_onto_existing_same_direction_positions():
    """Faz 361-devam — gerçek ZECUSDT örneği: 5x kaldıraçlı aynı sembol/
    yönde art arda 4-5 pozisyon, yön yanlış çıkınca leverage × yığın
    derinliği kadar büyüyen bir kayıp üretti (~$6.675). Artık
    ctx.risk.same_direction_open_counts'a göre kaldıraç orantılı düşüyor."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    symbol = "PYRLEVTESTUSDT"
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        original = repo.get("symbol_leverage")
        import json
        mapping = json.loads(original)
        mapping[symbol] = 5
        repo.set("symbol_leverage", json.dumps(mapping), updated_by="test")

    try:
        recorder = DecisionRecorder()
        entry_price = 100.0
        risk_mag = entry_price * 0.02  # dar stop -- max_safe_leverage 5x'i hiç sinirlamaz

        ctx = CognitiveCycleContext(
            market={"symbol": symbol, "raw_snapshot": {"close": entry_price}},
            decision={
                "proposed_direction": "LONG", "final_action": "LONG",
                "final_size": 100.0, "stop_loss_distance": risk_mag, "take_profit_distance": risk_mag,
            },
            risk={"evaluation": {"verdict": "approved"}, "same_direction_open_counts": {"LONG": 1}},
        )

        event = recorder.record(ctx, [])
        assert event.leverage == 2.5
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("symbol_leverage", original, updated_by="test")


def test_worse_price_pyramid_add_blocked_outside_allowed_regime():
    """Faz 361 — kullanıcı kararı: aynı sembol/yönde açık pozisyon
    varken daha kötü fiyattan üste eklemek SADECE bullish_low rejiminde
    izinli, diğer TÜM rejimlerde kesin olarak engellenmeli."""
    from database.session_factory import SessionFactory

    symbol = f"PYRTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    recorder = DecisionRecorder()

    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(_open_long_event(symbol, entry_price=100.0))

    ctx = CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 110.0},
            "features": {"trend": "bearish", "volatility_regime": "normal"},
        },
        decision={
            "proposed_direction": "LONG", "final_action": "LONG",
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )

    event = recorder.record(ctx, [])
    assert event.status == "no_trade"

    # Kullanıcı isteği (2026-08-31): bu kapı da diğer 7'siyle AYNI desende
    # artık görünürlük bırakıyor.
    gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block"]
    assert len(gate_blocks) == 1
    assert gate_blocks[0]["data"]["gate"] == "pyramid_regime_gate"
    assert gate_blocks[0]["data"]["market_regime"] == "bearish_normal"


def test_worse_price_pyramid_add_allowed_in_bullish_low_regime():
    from database.session_factory import SessionFactory

    symbol = f"PYRTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    recorder = DecisionRecorder()

    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(_open_long_event(symbol, entry_price=100.0))

    ctx = CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 110.0},
            "features": {"trend": "bullish", "volatility_regime": "low"},
        },
        decision={
            "proposed_direction": "LONG", "final_action": "LONG",
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )

    event = recorder.record(ctx, [])
    assert event.status == "open"


def _open_long_event(symbol: str, entry_price: float):
    from contracts.decision_event import DecisionEvent

    return DecisionEvent(
        symbol=symbol, proposed_direction="LONG", final_action="LONG", final_size=10.0,
        status="open", entry_price=entry_price, quantity=10.0,
        opened_at=datetime.now(UTC),
    )


def test_record_and_replay():
    recorder = DecisionRecorder()

    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )

    event = recorder.record(ctx, [])

    assert event.symbol == "BTCUSDT"
    assert event.final_action != ""

    session = get_session()

    try:
        persistor = DecisionPersistor(session)

        persistor.persist(event)

        replayed = recorder.replay(str(event.id))

        assert replayed is not None
        assert replayed.symbol == "BTCUSDT"

        decisions = recorder.list_decisions(limit=5)

        assert len(decisions) >= 1

    finally:
        session.close()
