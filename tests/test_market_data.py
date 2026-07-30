"""Market data testleri."""
import pytest
from market_data.ingestion.mock_adapter import MockOHLCVAdapter
from market_data.features.indicators import rsi, ema, macd

def test_mock_deterministic():
    a1 = MockOHLCVAdapter(seed=42)
    a2 = MockOHLCVAdapter(seed=42)
    d1 = a1.generate(10)
    d2 = a2.generate(10)
    assert [o.close for o in d1] == [o.close for o in d2]

def test_rsi_range():
    adapter = MockOHLCVAdapter()
    data = adapter.generate(20)
    val = rsi(data)
    assert 0 <= val <= 100

def test_ema_exists():
    adapter = MockOHLCVAdapter()
    data = adapter.generate(25)
    val = ema(data, 20)
    assert val > 0
