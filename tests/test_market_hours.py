"""Faz 195: piyasa saati farkındalığı — kripto her zaman açık, hisse/endeks
sadece NYSE/NASDAQ seans saatlerinde, emtia vadeli işlemleri kendi CME
takvimine göre."""
from datetime import datetime
from zoneinfo import ZoneInfo

from market_data.market_hours import is_market_open

_ET = ZoneInfo("America/New_York")


def test_crypto_is_always_open():
    midnight_saturday = datetime(2026, 8, 8, 3, 0, tzinfo=_ET)  # Cumartesi gece
    assert is_market_open("BTCUSDT", midnight_saturday) is True
    assert is_market_open("ETHUSDT", midnight_saturday) is True


def test_equity_closed_at_midnight_on_a_weekday():
    midnight_wednesday = datetime(2026, 8, 5, 2, 0, tzinfo=_ET)
    assert is_market_open("AAPL", midnight_wednesday) is False


def test_equity_open_during_regular_session():
    noon_wednesday = datetime(2026, 8, 5, 12, 0, tzinfo=_ET)
    assert is_market_open("AAPL", noon_wednesday) is True
    assert is_market_open("^GSPC", noon_wednesday) is True


def test_equity_closed_on_weekend():
    saturday_noon = datetime(2026, 8, 8, 12, 0, tzinfo=_ET)
    assert is_market_open("NVDA", saturday_noon) is False


def test_equity_closed_before_open_and_after_close():
    before_open = datetime(2026, 8, 5, 9, 0, tzinfo=_ET)
    after_close = datetime(2026, 8, 5, 16, 30, tzinfo=_ET)
    assert is_market_open("MSFT", before_open) is False
    assert is_market_open("MSFT", after_close) is False


def test_futures_open_on_a_weekday_afternoon():
    wednesday_noon = datetime(2026, 8, 5, 12, 0, tzinfo=_ET)
    assert is_market_open("GC=F", wednesday_noon) is True


def test_futures_closed_saturday():
    saturday_noon = datetime(2026, 8, 8, 12, 0, tzinfo=_ET)
    assert is_market_open("SI=F", saturday_noon) is False


def test_futures_closed_during_daily_maintenance_break():
    daily_break = datetime(2026, 8, 5, 17, 30, tzinfo=_ET)
    assert is_market_open("GC=F", daily_break) is False


def test_futures_open_sunday_evening():
    sunday_evening = datetime(2026, 8, 9, 19, 0, tzinfo=_ET)
    assert is_market_open("SI=F", sunday_evening) is True


def test_futures_closed_sunday_afternoon():
    sunday_afternoon = datetime(2026, 8, 9, 12, 0, tzinfo=_ET)
    assert is_market_open("GC=F", sunday_afternoon) is False


def test_unknown_symbol_defaults_to_open():
    ctx_time = datetime(2026, 8, 8, 3, 0, tzinfo=_ET)
    assert is_market_open("SOMECRYPTOTHATDOESNOTENDINUSDT", ctx_time) is True
