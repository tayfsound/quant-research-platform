"""Pump-Fade Strategy testleri — bkz. services/pump_fade_strategy.py.
Kullanıcı isteği: AI konsey/confidence sisteminden tamamen yalıtık, test
amaçlı mekanik bir strateji ("son iki günde %100 yapmış coinleri short'la,
kasanın %5'i kadar 5x pozisyona gir, %100 kâr ettiğinde çık")."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.pump_fade_strategy import EXPERIMENT_BUCKET, PumpFadeStrategy, find_pump_candidates


def _bar(low: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime.now(UTC), open=close, high=max(low, close), low=low, close=close, volume=1.0
    )


class _FakeProvider:
    def __init__(self, bars_by_symbol: dict):
        self.bars_by_symbol = bars_by_symbol

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return self.bars_by_symbol.get(symbol, [])


def _cleanup_symbol(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _set_pump_fade_settings(**overrides) -> None:
    defaults = {
        "pump_fade_enabled": "false",
        "pump_fade_capital_pct": "0.05",
        "pump_fade_leverage": "5",
        "pump_fade_min_gain_pct": "1.0",
        "pump_fade_lookback_hours": "48",
        "pump_fade_stop_distance_pct": "0.15",
        "starting_capital": "1000",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")


def test_find_pump_candidates_identifies_symbol_meeting_gain_threshold():
    provider = _FakeProvider({
        "PUMPUSDT": [_bar(10.0, 10.0), _bar(10.0, 22.0)],  # low=10, current=22 -> %120 kazanç
        "FLATUSDT": [_bar(10.0, 10.0), _bar(10.0, 10.5)],  # %5 kazanç, eşiğin altında
    })
    candidates = find_pump_candidates(["PUMPUSDT", "FLATUSDT"], provider, lookback_hours=48, min_gain_pct=1.0)
    assert {c["symbol"] for c in candidates} == {"PUMPUSDT"}
    assert candidates[0]["gain_pct"] == pytest.approx(1.2)


def test_find_pump_candidates_skips_symbols_when_fetch_fails():
    class _BrokenProvider:
        def get_ohlcv(self, symbol, timeframe, limit=100):
            raise RuntimeError("network down")

    candidates = find_pump_candidates(["BROKENUSDT"], _BrokenProvider(), lookback_hours=48, min_gain_pct=1.0)
    assert candidates == []


def test_find_pump_candidates_skips_symbols_with_insufficient_bars():
    provider = _FakeProvider({"THINUSDT": [_bar(10.0, 20.0)]})
    candidates = find_pump_candidates(["THINUSDT"], provider, lookback_hours=48, min_gain_pct=1.0)
    assert candidates == []


def test_run_cycle_skipped_when_disabled():
    _set_pump_fade_settings(pump_fade_enabled="false")
    result = PumpFadeStrategy(data_provider=_FakeProvider({})).run_cycle()
    assert result == {"skipped": "pump_fade_disabled"}


def test_run_cycle_opens_short_position_with_leverage_clamped_by_safety_lock(monkeypatch):
    """Varsayılan pump_fade_stop_distance_pct=0.15 ile max_safe_leverage
    hedef 5x'i ~4.35x'e kırpmalı — kullanıcının onayladığı güvenlik kilidi
    gerçekten uygulanıyor mu?"""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: [_bar(10.0, 10.0), _bar(10.0, 22.0)]})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["candidates_found"] == 1
        assert len(result["opened"]) == 1
        opened = result["opened"][0]
        assert opened["symbol"] == symbol
        assert 4.0 < opened["leverage"] < 5.0  # kırpılmış, ama 5x'e yakın

        with SessionFactory.get_session() as session:
            rows = DecisionPersistor(session).list_open_positions(limit=50)
        row = next(r for r in rows if r["symbol"] == symbol)
        assert row["direction"] == "SHORT"
        assert row["experiment_bucket"] == EXPERIMENT_BUCKET
        assert row["leverage"] == pytest.approx(opened["leverage"])
        # Güvenlik: likidasyon her zaman stop'tan daha uzakta kalmalı
        # (SHORT'ta ikisi de fiyatın YUKARI gitmesiyle tetiklenir).
        assert row["liquidation_price"] > row["stop_loss_price"] > row["entry_price"]
        # Çıkış kuralı: "%100 kâr ettiğinde" -> fiyat AŞAĞI inince kâr.
        assert row["take_profit_price"] < row["entry_price"]
        assert row["quantity"] > 0
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_open_a_second_position_for_a_symbol_already_open(monkeypatch):
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: [_bar(10.0, 10.0), _bar(10.0, 22.0)]})
        strategy = PumpFadeStrategy(data_provider=provider)

        first = strategy.run_cycle()
        second = strategy.run_cycle()

        assert len(first["opened"]) == 1
        assert len(second["opened"]) == 0
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_run_cycle_does_not_raise_target_leverage_when_safety_lock_would_allow_more(monkeypatch):
    """AI'daki AYNI ilke: configured/hedef kaldıraç sadece bir TAVAN,
    güvenlik kilidi daha yüksek bir kaldıraca asla izin vermek için
    kullanılmaz (sadece sıkılaştırır, asla gevşetmez)."""
    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        _set_pump_fade_settings(pump_fade_enabled="true", pump_fade_stop_distance_pct="0.01")
        monkeypatch.setattr(
            "services.pump_fade_strategy.fetch_usdt_perpetual_symbols", lambda: [symbol]
        )
        provider = _FakeProvider({symbol: [_bar(10.0, 10.0), _bar(10.0, 22.0)]})

        result = PumpFadeStrategy(data_provider=provider).run_cycle()

        assert result["opened"][0]["leverage"] == pytest.approx(5.0)
    finally:
        _cleanup_symbol(symbol)
        _set_pump_fade_settings(pump_fade_enabled="false")


def test_list_closed_trades_exclude_experiment_bucket_filters_out_that_bucket_only():
    from datetime import UTC, datetime, timedelta

    from contracts.decision_event import DecisionEvent

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=26)
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            ai_event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
            )
            repo.persist(ai_event)
            repo.close_position(decision_id=str(ai_event.id), exit_price=105.0, pnl=5.0, closed_at=far_future)

            pf_event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            )
            repo.persist(pf_event)
            repo.close_position(
                decision_id=str(pf_event.id), exit_price=90.0, pnl=10.0, closed_at=far_future + timedelta(seconds=1)
            )

            unfiltered = repo.list_closed_trades(limit=10)
            filtered = repo.list_closed_trades(limit=10, exclude_experiment_bucket=EXPERIMENT_BUCKET)

        unfiltered_symbols_ids = {str(r["id"]) for r in unfiltered if r["symbol"] == symbol}
        filtered_ids = {str(r["id"]) for r in filtered if r["symbol"] == symbol}
        assert unfiltered_symbols_ids == {str(ai_event.id), str(pf_event.id)}
        assert filtered_ids == {str(ai_event.id)}
    finally:
        _cleanup_symbol(symbol)


def test_has_open_position_for_experiment_reflects_real_open_positions():
    from contracts.decision_event import DecisionEvent

    symbol = f"PUMPFADE{uuid4().hex[:8]}USDT"
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            assert repo.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET) is False
            repo.persist(DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
                final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                experiment_bucket=EXPERIMENT_BUCKET,
            ))
            assert repo.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET) is True
            assert repo.has_open_position_for_experiment(symbol, "some_other_experiment") is False
    finally:
        _cleanup_symbol(symbol)
