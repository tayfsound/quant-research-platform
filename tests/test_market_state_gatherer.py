"""Faz 401 — services/market_state_gatherer.py. tests/
test_belief_reversal_exit.py'deki AYNI RoutingProvider mock deseni."""
from datetime import UTC, datetime, timedelta

from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.market_state_gatherer import gather_market_state_cluster


def _bars(closes: list[float]) -> list[OHLCV]:
    now = datetime.now(UTC)
    return [
        OHLCV(timestamp=now + timedelta(minutes=15 * i), open=c, high=c, low=c, close=c, volume=100.0)
        for i, c in enumerate(closes)
    ]


class _FakeProvider:
    def __init__(self, bars_by_symbol: dict[str, list[OHLCV]]):
        self._bars_by_symbol = bars_by_symbol

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[OHLCV]:
        return self._bars_by_symbol.get(symbol, [])


def _set_watchlist(symbols: list[str]) -> str:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        original = repo.get("watchlist")
        repo.set("watchlist", ",".join(symbols), updated_by="test")
    return original


def _restore_watchlist(original: str) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("watchlist", original, updated_by="test")


def test_gathers_market_state_for_every_watchlist_symbol_with_enough_bars(monkeypatch):
    original = _set_watchlist(["AAATESTUSDT", "BBBTESTUSDT"])
    try:
        base = [100.0 + i * 0.1 for i in range(30)]
        provider = _FakeProvider({
            "AAATESTUSDT": _bars(base),
            "BBBTESTUSDT": _bars([c * 1.01 for c in base]),  # neredeyse özdeş -> yüksek korele
        })
        monkeypatch.setattr("market_data.ingestion.data_provider.RoutingProvider", lambda: provider)

        result = gather_market_state_cluster()

        assert result["n_symbols"] == 2
        assert "AAATESTUSDT" in result["by_symbol"]
        assert "BBBTESTUSDT" in result["by_symbol"]
        # 30 bar < 220 -> long_term_trend_regime="insufficient_data" -> NEUTRAL,
        # ama küme alanları (yüksek korele eş) yine de dolu olmalı.
        assert result["by_symbol"]["AAATESTUSDT"]["direction"] == "NEUTRAL"
        assert result["by_symbol"]["AAATESTUSDT"]["peer_count"] == 1
    finally:
        _restore_watchlist(original)


def test_symbols_with_too_few_bars_are_skipped_not_invented(monkeypatch):
    original = _set_watchlist(["CCCTESTUSDT", "DDDTESTUSDT"])
    try:
        provider = _FakeProvider({
            "CCCTESTUSDT": _bars([100.0, 101.0]),  # tek getiri -> min 2 gerekiyor
            "DDDTESTUSDT": [],
        })
        monkeypatch.setattr("market_data.ingestion.data_provider.RoutingProvider", lambda: provider)

        result = gather_market_state_cluster()

        assert result["by_symbol"] == {}
        assert result["n_symbols"] == 0
    finally:
        _restore_watchlist(original)


def test_provider_exception_for_one_symbol_does_not_break_the_others(monkeypatch):
    original = _set_watchlist(["EEETESTUSDT", "FFFTESTUSDT"])
    try:
        base = [100.0 + i * 0.1 for i in range(30)]

        class _PartiallyFailingProvider:
            def get_ohlcv(self, symbol, timeframe, limit=100):
                if symbol == "EEETESTUSDT":
                    raise ConnectionError("simulated network failure")
                return _bars(base)

        monkeypatch.setattr(
            "market_data.ingestion.data_provider.RoutingProvider", lambda: _PartiallyFailingProvider(),
        )

        result = gather_market_state_cluster()

        assert "FFFTESTUSDT" in result["by_symbol"]
        assert "EEETESTUSDT" not in result["by_symbol"]
    finally:
        _restore_watchlist(original)
