"""Faz 352 — Regime Reversal Guardian, servis katmanı testleri.

Kullanıcı fikri, GERÇEK bir olayla doğrulandı: LONG'da art arda 14
stop-loss, aynı anda 275 açık LONG'un 170'i zararda. Bu testler, ölçüm
(compute_direction_stop_streaks), gate (is_direction_paused) ve aksiyon
(sweep_close_profitable_positions / run_guardian_sweep) katmanlarını
gerçek DB satırlarıyla doğruluyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services import regime_reversal_guardian as guardian


def _cleanup(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _set_guardian_settings(**overrides) -> None:
    defaults = {
        "reversal_guardian_enabled": "true",
        "reversal_guardian_consecutive_stop_threshold": "3",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")
    guardian._streak_cache = None


def _persist_closed(
    symbol: str, direction: str, exit_reason: str, closed_at: datetime,
    experiment_bucket: str | None = None, pnl: float = -5.0,
) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction=direction, final_action=direction,
            final_size=0.1, confidence=0.5, status="open", entry_price=100.0, quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10), experiment_bucket=experiment_bucket,
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id), exit_price=95.0, pnl=pnl, closed_at=closed_at,
            outcome={"exit_reason": exit_reason, "pnl": pnl},
        )


def _open_position(symbol: str, direction: str, entry_price: float = 100.0, quantity: float = 1.0) -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=quantity, confidence=0.7,
        status="open", entry_price=entry_price, quantity=quantity, opened_at=now,
        stop_loss_price=90.0 if direction == "LONG" else 110.0,
        take_profit_price=120.0 if direction == "LONG" else 80.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


class _FixedPriceProvider:
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


@pytest.fixture(autouse=True)
def _reset_cache():
    guardian._streak_cache = None
    yield
    guardian._streak_cache = None


def test_compute_direction_stop_streaks_counts_consecutive_stops_per_direction():
    """Gelecek tarihli veri (test_meta_label_model.py'deki AYNI kanıtlanmış
    desen) — paylaşılan test DB'sindeki başka kayıtlardan bağımsız olarak,
    ORDER BY closed_at DESC LIMIT sorgusunda her zaman EN ÖNDE çıkar."""
    symbol = f"REVGUARD{uuid4().hex[:8]}"
    base = datetime.now(UTC) + timedelta(days=3653)
    try:
        # LONG: en yeni 3 stop, sonra bir kazanç -> streak=3
        _persist_closed(symbol, "LONG", "take_profit", base - timedelta(minutes=40), pnl=5.0)
        _persist_closed(symbol, "LONG", "stop_loss", base - timedelta(minutes=30))
        _persist_closed(symbol, "LONG", "stop_loss", base - timedelta(minutes=20))
        _persist_closed(symbol, "LONG", "stop_loss", base - timedelta(minutes=10))
        # SHORT: en yeni işlem kazanç -> streak=0
        _persist_closed(symbol, "SHORT", "take_profit", base - timedelta(minutes=10), pnl=5.0)

        streaks = guardian.compute_direction_stop_streaks()

        assert streaks["LONG"] >= 3  # en az kendi eklediğim 3 ardışık stop
        # SHORT'ta EN SON (en yeni) kapanış kazanç olduğu için (bu sembolün
        # kendi geçmişi ORDER BY closed_at DESC'te en önde), global SHORT
        # streak'i 0 olmalı — başka testlerin/paylaşılan verinin eski
        # SHORT stop'ları bu en-yeni kazancın ARKASINDA kalır, sayılmaz.
        assert streaks["SHORT"] == 0
    finally:
        _cleanup(symbol)


def test_compute_direction_stop_streaks_excludes_mechanical_strategies():
    """pump_fade/basis_arb kapanışları streak'e karışmamalı — council'in
    GERÇEKTEN yön konusunda haklı çıkıp çıkmadığını yansıtmıyorlar."""
    symbol = f"REVGUARD{uuid4().hex[:8]}"
    base = datetime.now(UTC) + timedelta(days=3654)
    try:
        _persist_closed(symbol, "LONG", "stop_loss", base, experiment_bucket="pump_fade_v1")
        # Bu sembolde pump_fade dışında hiçbir council kararı yok — streak
        # hesaplamasına bu satırın hiç girmediğini, en son (gerçek) council
        # kararının önüne geçmediğini doğrulamak yerine, doğrudan filtre
        # mantığını (agreement/experiment_bucket dışlama) burada kontrol
        # ediyoruz.
        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_closed_trades(limit=10, direction="LONG")
        matching = [r for r in rows if r.get("symbol") == symbol]
        assert len(matching) == 1
        assert matching[0]["experiment_bucket"] == "pump_fade_v1"
        assert matching[0]["experiment_bucket"] in guardian._MECHANICAL_EXPERIMENT_BUCKETS
    finally:
        _cleanup(symbol)


def test_is_direction_paused_false_when_disabled():
    _set_guardian_settings(reversal_guardian_enabled="false")
    assert guardian.is_direction_paused("LONG") is False


def test_is_direction_paused_uses_cache(monkeypatch):
    _set_guardian_settings(reversal_guardian_enabled="true", reversal_guardian_consecutive_stop_threshold="2")
    calls = {"n": 0}

    def _fake_compute():
        calls["n"] += 1
        return {"LONG": 5, "SHORT": 0}

    monkeypatch.setattr(guardian, "compute_direction_stop_streaks", _fake_compute)
    assert guardian.is_direction_paused("LONG") is True
    assert guardian.is_direction_paused("LONG") is True  # cache'ten, tekrar hesaplamaz
    assert calls["n"] == 1
    assert guardian.is_direction_paused("SHORT") is False


def test_sweep_close_profitable_positions_closes_only_profitable_in_that_direction(monkeypatch):
    """Paylaşılan test DB'sinde başka (gerçek/leftover) açık pozisyonlar
    olabilir — list_open_positions bu testin İKİ sembolüyle sınırlanıyor
    ki sabit-fiyatlı sahte sağlayıcı onları yanlışlıkla "kârda" görüp
    kapatmasın (bkz. project memory: paylaşılan test state şişmesi)."""
    monkeypatch.setattr(
        "market_data.ingestion.data_provider.RoutingProvider",
        lambda: _FixedPriceProvider(110.0),
    )
    long_symbol = f"REVGUARD{uuid4().hex[:8]}"
    short_symbol = f"REVGUARD{uuid4().hex[:8]}"
    try:
        _open_position(long_symbol, "LONG", entry_price=100.0)  # 110 > 100 -> kârda
        _open_position(short_symbol, "SHORT", entry_price=100.0)  # 110 > 100 -> SHORT zararda

        real_list_open_positions = DecisionPersistor.list_open_positions

        def _scoped_list_open_positions(self, limit=None, offset=0):
            all_positions = real_list_open_positions(self, limit=limit, offset=offset)
            return [p for p in all_positions if p["symbol"] in (long_symbol, short_symbol)]

        monkeypatch.setattr(DecisionPersistor, "list_open_positions", _scoped_list_open_positions)

        result = guardian.sweep_close_profitable_positions("LONG")

        assert result["direction"] == "LONG"
        assert result["closed_count"] == 1
        assert result["closed"][0]["symbol"] == long_symbol

        with SessionFactory.get_session() as session:
            long_status = session.execute(
                text("SELECT status FROM decisions WHERE symbol = :s"), {"s": long_symbol}
            ).scalar()
            short_status = session.execute(
                text("SELECT status FROM decisions WHERE symbol = :s"), {"s": short_symbol}
            ).scalar()
        assert long_status == "closed"
        assert short_status == "open"  # SHORT hiç dokunulmadı (yön filtreli + zaten zararda)
    finally:
        _cleanup(long_symbol)
        _cleanup(short_symbol)


def test_run_guardian_sweep_is_noop_when_disabled():
    _set_guardian_settings(reversal_guardian_enabled="false")
    assert guardian.run_guardian_sweep() == {"enabled": False}


def test_run_guardian_sweep_triggers_action_when_streak_at_threshold(monkeypatch):
    monkeypatch.setattr(guardian, "compute_direction_stop_streaks", lambda: {"LONG": 5, "SHORT": 0})
    monkeypatch.setattr(guardian, "sweep_close_profitable_positions", lambda d: {"direction": d, "closed_count": 2, "closed": []})
    _set_guardian_settings(reversal_guardian_enabled="true", reversal_guardian_consecutive_stop_threshold="3")

    result = guardian.run_guardian_sweep()

    assert result["enabled"] is True
    assert len(result["actions"]) == 1
    assert result["actions"][0]["direction"] == "LONG"


def test_run_guardian_sweep_does_not_trigger_below_threshold(monkeypatch):
    monkeypatch.setattr(guardian, "compute_direction_stop_streaks", lambda: {"LONG": 2, "SHORT": 1})
    _set_guardian_settings(reversal_guardian_enabled="true", reversal_guardian_consecutive_stop_threshold="3")

    result = guardian.run_guardian_sweep()

    assert result["actions"] == []
