"""Faz 194: YahooProvider — kripto-olmayan varlıklar (endeks/emtia/hisse)
için gerçek OHLCV kaynağı. Gerçek ağa karşı test ediyor (Binance testlerinde
zaten kurulmuş konvansiyonla tutarlı — tests/test_market_data_provider.py:
test_binance_provider_works_from_inside_a_running_event_loop)."""
from market_data.ingestion.ohlcv import OHLCV
from market_data.ingestion.yahoo_provider import YahooProvider


def test_yahoo_provider_fetches_real_daily_bars_for_a_real_stock():
    data = YahooProvider().get_ohlcv("AAPL", "1d", limit=5)
    assert len(data) <= 5
    assert len(data) > 0
    assert isinstance(data[0], OHLCV)
    assert data[-1].close > 0


def test_yahoo_provider_fetches_real_index_data():
    data = YahooProvider().get_ohlcv("^GSPC", "1d", limit=3)
    assert len(data) > 0
    assert data[-1].close > 100  # S&P 500 seviyesi, gerçekçi bir alt sınır


def test_yahoo_provider_returns_empty_list_for_a_nonexistent_ticker():
    data = YahooProvider().get_ohlcv("THISISNOTAREALTICKERXYZ123", "1d", limit=5)
    assert data == []
