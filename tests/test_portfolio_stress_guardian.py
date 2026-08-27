"""Backlog #13 (2026-08-26) — Portfolio Stress Guardian testleri.

Kullanıcı örneği: "70 pozisyon +20k kârda, 30'u riskli, kötüye giderse
-50k olabilir — şimdi hepsini kapatıp +2k'da kalmak -50k'dan iyidir."
Bu testler, GERÇEK tarihsel en-kötü-N-günlük senaryonun mevcut açık
pozisyonlara doğru uygulandığını ve tetiklendiğinde HEPSİNİN (yön/
strateji fark etmeksizin) kapatıldığını doğruluyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services import portfolio_stress_guardian as guardian


def _cleanup(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _set_settings(**overrides) -> None:
    defaults = {
        "portfolio_stress_guardian_enabled": "true",
        "portfolio_stress_guardian_window_days": "7",
        "portfolio_stress_guardian_reference_symbol": "BTCUSDT",
        "portfolio_stress_guardian_history_days": "365",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")


def _open_position(symbol: str, direction: str, entry_price: float, quantity: float) -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=quantity, confidence=0.7,
        status="open", entry_price=entry_price, quantity=quantity, opened_at=now,
        stop_loss_price=entry_price * (0.5 if direction == "LONG" else 1.5),
        take_profit_price=entry_price * (1.5 if direction == "LONG" else 0.5),
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


class _FixedPriceProvider:
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def _bar(days_ago: int, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime.now(UTC) - timedelta(days=days_ago),
        open=close, high=close, low=close, close=close, volume=1.0,
    )


def _crash_history_bars(crash_pct: float = 0.5, window: int = 7, flat_days: int = 5) -> list[OHLCV]:
    """flat_days gun sabit fiyat, sonra window gun boyunca toplamda
    crash_pct kadar dusen (her gun ayni oranda) bir seri — compute_
    worst_historical_drawdown'un GERCEKTEN -crash_pct'i bulmasi icin."""
    daily_factor = (1 - crash_pct) ** (1 / window)
    bars = []
    price = 100.0
    total_days = flat_days + window
    for i in range(total_days, 0, -1):
        bars.append(_bar(i, price))
        if i <= window:
            price *= daily_factor
    bars.append(_bar(0, price))
    return bars


class _HistoryProvider:
    def __init__(self, bars: list[OHLCV]):
        self.bars = bars

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return self.bars[-limit:] if limit < len(self.bars) else self.bars


def test_compute_portfolio_stress_projection_flags_crash_scenario(monkeypatch):
    """LONG pozisyon, gercek -%50'lik 7-gunluk tarihsel dususe maruz
    kalirsa mevcut kucuk kari buyuk zarara cevirmeli."""
    symbol = f"STRESSGRD{uuid4().hex[:8]}"
    try:
        _open_position(symbol, "LONG", entry_price=100.0, quantity=1000.0)  # notional=100,000

        real_list_open_positions = DecisionPersistor.list_open_positions

        def _scoped(self, limit=None, offset=0):
            all_positions = real_list_open_positions(self, limit=limit, offset=offset)
            return [p for p in all_positions if p["symbol"] == symbol]

        monkeypatch.setattr(DecisionPersistor, "list_open_positions", _scoped)
        monkeypatch.setattr(
            "market_data.ingestion.data_provider.get_ohlcv_provider",
            lambda: _HistoryProvider(_crash_history_bars(crash_pct=0.5, window=7)),
        )
        monkeypatch.setattr(
            "services.position_closer.fetch_current_prices_by_symbol",
            lambda symbols: {symbol: 110.0},  # su an +%10 karda
        )
        _set_settings()

        projection = guardian.compute_portfolio_stress_projection()

        assert projection is not None
        assert projection["current_unrealized_pnl"] == pytest.approx(10_000.0, rel=0.01)
        assert projection["long_notional"] == pytest.approx(100_000.0, rel=0.01)
        assert projection["short_notional"] == 0.0
        assert projection["worst_down_pct"] == pytest.approx(-0.5, rel=0.02)
        # crash senaryosu: 10_000 + (-0.5 * 100_000) = -40_000
        assert projection["scenario_crash_pnl"] == pytest.approx(-40_000.0, rel=0.02)
        assert projection["worst_case_projected_pnl"] < 0
        assert guardian.is_triage_triggered(projection) is True
    finally:
        _cleanup(symbol)


def test_compute_portfolio_stress_projection_not_triggered_when_already_at_a_loss(monkeypatch):
    """Su an zaten net zarardaysa (stres olmadan bile) mekanizma devreye
    girmemeli — bu farkli bir problem, kendi stop/hedeflerine birakilmis."""
    symbol = f"STRESSGRD{uuid4().hex[:8]}"
    try:
        _open_position(symbol, "LONG", entry_price=100.0, quantity=1000.0)

        real_list_open_positions = DecisionPersistor.list_open_positions

        def _scoped(self, limit=None, offset=0):
            all_positions = real_list_open_positions(self, limit=limit, offset=offset)
            return [p for p in all_positions if p["symbol"] == symbol]

        monkeypatch.setattr(DecisionPersistor, "list_open_positions", _scoped)
        monkeypatch.setattr(
            "market_data.ingestion.data_provider.get_ohlcv_provider",
            lambda: _HistoryProvider(_crash_history_bars(crash_pct=0.5, window=7)),
        )
        monkeypatch.setattr(
            "services.position_closer.fetch_current_prices_by_symbol",
            lambda symbols: {symbol: 90.0},  # su an zaten zararda
        )
        _set_settings()

        projection = guardian.compute_portfolio_stress_projection()
        assert projection["current_unrealized_pnl"] < 0
        assert guardian.is_triage_triggered(projection) is False
    finally:
        _cleanup(symbol)


def test_run_portfolio_triage_sweep_is_noop_when_disabled():
    _set_settings(portfolio_stress_guardian_enabled="false")
    assert guardian.run_portfolio_triage_sweep() == {"enabled": False}


def test_run_portfolio_triage_sweep_closes_all_positions_when_triggered(monkeypatch):
    """Tetiklendiginde HEM kardaki HEM zarardaki pozisyonlar (yon fark
    etmeksizin) kapatilmali — Regime Reversal Guardian'in aksine sadece
    kardakiler degil, sistemik bir mudahale."""
    long_symbol = f"STRESSGRD{uuid4().hex[:8]}"
    short_symbol = f"STRESSGRD{uuid4().hex[:8]}"
    try:
        _open_position(long_symbol, "LONG", entry_price=100.0, quantity=1000.0)
        _open_position(short_symbol, "SHORT", entry_price=100.0, quantity=50.0)  # bu zararda kalacak

        real_list_open_positions = DecisionPersistor.list_open_positions

        def _scoped(self, limit=None, offset=0):
            all_positions = real_list_open_positions(self, limit=limit, offset=offset)
            return [p for p in all_positions if p["symbol"] in (long_symbol, short_symbol)]

        monkeypatch.setattr(DecisionPersistor, "list_open_positions", _scoped)
        monkeypatch.setattr(
            "market_data.ingestion.data_provider.get_ohlcv_provider",
            lambda: _HistoryProvider(_crash_history_bars(crash_pct=0.5, window=7)),
        )
        monkeypatch.setattr(
            "services.position_closer.fetch_current_prices_by_symbol",
            lambda symbols: {long_symbol: 110.0, short_symbol: 110.0},
        )
        monkeypatch.setattr(
            "market_data.ingestion.data_provider.RoutingProvider",
            lambda: _FixedPriceProvider(110.0),
        )
        _set_settings()

        result = guardian.run_portfolio_triage_sweep()

        assert result["enabled"] is True
        assert result["triggered"] is True
        assert result["sweep"]["closed_count"] == 2

        with SessionFactory.get_session() as session:
            statuses = {
                row.symbol: row.status
                for row in session.execute(
                    text("SELECT symbol, status FROM decisions WHERE symbol = ANY(:syms)"),
                    {"syms": [long_symbol, short_symbol]},
                )
            }
        assert statuses[long_symbol] == "closed"
        assert statuses[short_symbol] == "closed"  # zarardaki bacak da kapandi
    finally:
        _cleanup(long_symbol)
        _cleanup(short_symbol)
