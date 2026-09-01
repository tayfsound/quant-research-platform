"""Faz 403 — Market State Reversal Guardian, servis katmanı testleri.
tests/test_belief_reversal_exit.py'deki AYNI test deseni (farkı: council'in
kendi ardışık oyları yerine, kaydedilmiş bir market_state_snapshots
raporu kullanıyor)."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from contracts.market_state_report import MarketStateReport
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.market_state_report_repository import (
    MarketStateReportModel,
    MarketStateReportRepository,
)
from database.session_factory import SessionFactory
from services import market_state_reversal_guardian as guardian


def _cleanup_symbol(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _cleanup_report(report_id) -> None:
    with SessionFactory.get_session() as session:
        session.query(MarketStateReportModel).filter_by(id=report_id).delete()
        session.commit()


def _set_settings(**overrides) -> None:
    defaults = {
        "market_state_reversal_guardian_enabled": "true",
        "market_state_reversal_guardian_min_confidence": "0.5",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")


def _open_position(symbol: str, direction: str, entry_price: float = 100.0, experiment_bucket=None) -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=1.0, confidence=0.7,
        status="open", entry_price=entry_price, quantity=1.0, opened_at=now,
        experiment_bucket=experiment_bucket,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def _save_report(by_symbol: dict) -> MarketStateReport:
    report = MarketStateReport(result={"by_symbol": by_symbol, "n_symbols": len(by_symbol)})
    with SessionFactory.get_session() as session:
        MarketStateReportRepository(session).save(report)
    return report


def _scope_open_positions(monkeypatch, *symbols):
    real_list_open_positions = DecisionPersistor.list_open_positions

    def _scoped(self, limit=None, offset=0):
        all_positions = real_list_open_positions(self, limit=limit, offset=offset)
        return [p for p in all_positions if p["symbol"] in symbols]

    monkeypatch.setattr(DecisionPersistor, "list_open_positions", _scoped)


def test_triggers_when_market_state_reverses_against_an_open_long(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({symbol: {"direction": "SHORT", "confidence": 0.7, "reversing": True, "regime_label": "x"}})
    try:
        _open_position(symbol, "LONG")
        _scope_open_positions(monkeypatch, symbol)

        triggered = guardian.find_reversal_triggered_positions(min_confidence=0.5)

        assert len(triggered) == 1
        assert triggered[0]["symbol"] == symbol
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


def test_not_triggered_when_market_state_agrees_with_the_position(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({symbol: {"direction": "LONG", "confidence": 0.9, "reversing": True, "regime_label": "x"}})
    try:
        _open_position(symbol, "LONG")
        _scope_open_positions(monkeypatch, symbol)

        assert guardian.find_reversal_triggered_positions(min_confidence=0.5) == []
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


def test_not_triggered_when_not_reversing(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({symbol: {"direction": "SHORT", "confidence": 0.9, "reversing": False, "regime_label": "x"}})
    try:
        _open_position(symbol, "LONG")
        _scope_open_positions(monkeypatch, symbol)

        assert guardian.find_reversal_triggered_positions(min_confidence=0.5) == []
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


def test_not_triggered_below_confidence_threshold(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({symbol: {"direction": "SHORT", "confidence": 0.3, "reversing": True, "regime_label": "x"}})
    try:
        _open_position(symbol, "LONG")
        _scope_open_positions(monkeypatch, symbol)

        assert guardian.find_reversal_triggered_positions(min_confidence=0.5) == []
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


def test_not_triggered_when_symbol_missing_from_the_report(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({"UNRELATEDUSDT": {"direction": "SHORT", "confidence": 0.9, "reversing": True}})
    try:
        _open_position(symbol, "LONG")
        _scope_open_positions(monkeypatch, symbol)

        assert guardian.find_reversal_triggered_positions(min_confidence=0.5) == []
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


def test_excludes_mechanical_strategies(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({symbol: {"direction": "SHORT", "confidence": 0.9, "reversing": True, "regime_label": "x"}})
    try:
        _open_position(symbol, "LONG", experiment_bucket="pump_fade_v1")
        _scope_open_positions(monkeypatch, symbol)

        assert guardian.find_reversal_triggered_positions(min_confidence=0.5) == []
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


def test_no_report_at_all_is_fail_closed_not_invented(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    try:
        _open_position(symbol, "LONG")
        _scope_open_positions(monkeypatch, symbol)

        assert guardian.find_reversal_triggered_positions(min_confidence=0.5) == []
    finally:
        _cleanup_symbol(symbol)


def test_sweep_is_noop_when_disabled():
    _set_settings(market_state_reversal_guardian_enabled="false")
    assert guardian.sweep_market_state_reversals() == {"enabled": False}


def test_sweep_partially_closes_the_triggered_position(monkeypatch):
    symbol = f"MSTREV{uuid4().hex[:8]}USDT"
    report = _save_report({symbol: {"direction": "SHORT", "confidence": 0.7, "reversing": True, "regime_label": "x"}})
    try:
        _set_settings()
        _open_position(symbol, "LONG", entry_price=100.0)
        _scope_open_positions(monkeypatch, symbol)

        class _FixedPriceProvider:
            def get_ohlcv(self, sym, timeframe, limit=1):
                from market_data.ingestion.ohlcv import OHLCV
                t = datetime.now(UTC)
                return [OHLCV(timestamp=t, open=105.0, high=105.0, low=105.0, close=105.0, volume=1.0)]

        monkeypatch.setattr(
            "market_data.ingestion.data_provider.RoutingProvider", lambda: _FixedPriceProvider()
        )

        result = guardian.sweep_market_state_reversals()

        assert result["enabled"] is True
        assert len(result["closed"]) == 1
        assert result["closed"][0]["symbol"] == symbol
        assert result["closed"][0]["market_state_direction"] == "SHORT"

        # Faz 403 -- kasıtlı olarak KISMİ (%50) kapatma, tam değil.
        with SessionFactory.get_session() as session:
            row = session.execute(
                text("SELECT status, quantity FROM decisions WHERE symbol=:s"), {"s": symbol}
            ).first()
        assert row.status == "open"
        assert row.quantity == pytest.approx(0.5)
    finally:
        _cleanup_symbol(symbol)
        _cleanup_report(report.id)


@pytest.fixture(autouse=True)
def _restore_default_settings():
    yield
    _set_settings(market_state_reversal_guardian_enabled="false")
