"""Faz 362-devam — Belief Reversal Exit, servis katmanı testleri.

Kullanıcı fikri: council elimde açık pozisyon varken art arda (>=N,
confidence>=eşik) tersine dönerse defansif çıkış tetiklenmeli. Geniş
örneklemli gerçek veriyle (10-24 Ağustos, 3619 pozisyon) doğrulandı --
bkz. analytics/signal_persistence.py başlığındaki tam tablo."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services import belief_reversal_exit as reversal_exit


def _cleanup(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _set_settings(**overrides) -> None:
    defaults = {
        "belief_reversal_exit_enabled": "true",
        "belief_reversal_exit_min_consistent_cycles": "3",
        "belief_reversal_exit_min_confidence": "0.65",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")


def _open_position(symbol: str, direction: str, entry_price: float = 100.0) -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=1.0, confidence=0.7,
        status="open", entry_price=entry_price, quantity=1.0, opened_at=now,
        stop_loss_price=90.0 if direction == "LONG" else 110.0,
        take_profit_price=120.0 if direction == "LONG" else 80.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def _persist_signal(symbol: str, direction: str, confidence: float, when: datetime) -> None:
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(DecisionEvent(
            symbol=symbol, proposed_direction=direction, final_action=direction,
            confidence=confidence, status="no_trade", timestamp=when,
        ))


def _scope_open_positions(monkeypatch, *symbols):
    real_list_open_positions = DecisionPersistor.list_open_positions

    def _scoped(self, limit=None, offset=0):
        all_positions = real_list_open_positions(self, limit=limit, offset=offset)
        return [p for p in all_positions if p["symbol"] in symbols]

    monkeypatch.setattr(DecisionPersistor, "list_open_positions", _scoped)


def test_find_reversal_triggered_positions_triggers_when_run_meets_minimum(monkeypatch):
    symbol = f"REVEXIT{uuid4().hex[:8]}USDT"
    try:
        _open_position(symbol, "LONG")
        now = datetime.now(UTC)
        for i in range(3):
            _persist_signal(symbol, "SHORT", 0.9, now + timedelta(minutes=i + 1))
        _scope_open_positions(monkeypatch, symbol)

        triggered = reversal_exit.find_reversal_triggered_positions(min_cycles=3, min_confidence=0.65)

        assert len(triggered) == 1
        assert triggered[0]["symbol"] == symbol
        assert triggered[0]["reversal_run_length"] == 3
    finally:
        _cleanup(symbol)


def test_find_reversal_triggered_positions_not_triggered_below_minimum(monkeypatch):
    symbol = f"REVEXIT{uuid4().hex[:8]}USDT"
    try:
        _open_position(symbol, "LONG")
        now = datetime.now(UTC)
        for i in range(2):  # esik 3, sadece 2 ardisik
            _persist_signal(symbol, "SHORT", 0.9, now + timedelta(minutes=i + 1))
        _scope_open_positions(monkeypatch, symbol)

        triggered = reversal_exit.find_reversal_triggered_positions(min_cycles=3, min_confidence=0.65)

        assert triggered == []
    finally:
        _cleanup(symbol)


def test_find_reversal_triggered_positions_excludes_mechanical_strategies(monkeypatch):
    symbol = f"REVEXIT{uuid4().hex[:8]}USDT"
    try:
        now = datetime.now(UTC)
        event = DecisionEvent(
            id=uuid4(), timestamp=now, symbol=symbol,
            proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
            status="open", entry_price=100.0, quantity=1.0, opened_at=now,
            experiment_bucket="pump_fade_v1",
        )
        with SessionFactory.get_session() as session:
            DecisionPersistor(session).persist(event)
        for i in range(5):
            _persist_signal(symbol, "SHORT", 0.9, now + timedelta(minutes=i + 1))
        _scope_open_positions(monkeypatch, symbol)

        triggered = reversal_exit.find_reversal_triggered_positions(min_cycles=3, min_confidence=0.65)

        assert triggered == []
    finally:
        _cleanup(symbol)


def test_sweep_reversal_exits_is_noop_when_disabled():
    _set_settings(belief_reversal_exit_enabled="false")
    assert reversal_exit.sweep_reversal_exits() == {"enabled": False}


def test_sweep_reversal_exits_closes_triggered_position(monkeypatch):
    symbol = f"REVEXIT{uuid4().hex[:8]}USDT"
    try:
        _set_settings(
            belief_reversal_exit_enabled="true",
            belief_reversal_exit_min_consistent_cycles="3",
            belief_reversal_exit_min_confidence="0.65",
        )
        _open_position(symbol, "LONG", entry_price=100.0)
        now = datetime.now(UTC)
        for i in range(3):
            _persist_signal(symbol, "SHORT", 0.9, now + timedelta(minutes=i + 1))
        _scope_open_positions(monkeypatch, symbol)

        class _FixedPriceProvider:
            def get_ohlcv(self, sym, timeframe, limit=1):
                from market_data.ingestion.ohlcv import OHLCV
                t = datetime.now(UTC)
                return [OHLCV(timestamp=t, open=105.0, high=105.0, low=105.0, close=105.0, volume=1.0)]

        monkeypatch.setattr(
            "market_data.ingestion.data_provider.RoutingProvider", lambda: _FixedPriceProvider()
        )

        result = reversal_exit.sweep_reversal_exits()

        assert result["enabled"] is True
        assert len(result["closed"]) == 1
        assert result["closed"][0]["symbol"] == symbol

        with SessionFactory.get_session() as session:
            status = session.execute(
                text("SELECT status FROM decisions WHERE symbol=:s AND status='closed'"), {"s": symbol}
            ).scalar()
        assert status == "closed"
    finally:
        _cleanup(symbol)


@pytest.fixture(autouse=True)
def _restore_default_settings():
    yield
    _set_settings()
