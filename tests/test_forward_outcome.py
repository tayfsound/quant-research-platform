from services.forward_outcome import ForwardOutcome
from market_data.ingestion.mock_adapter import MockOHLCVAdapter

def test_long_win_when_price_rises():
    adapter = MockOHLCVAdapter(seed=42)
    data = adapter.generate(20)
    fo = ForwardOutcome(bars_forward=10)
    result = fo.calculate(data[0].close, "LONG", data)
    assert "pnl" in result
    assert "win" in result

def test_short_win_when_price_falls():
    adapter = MockOHLCVAdapter(seed=42)
    data = adapter.generate(20)
    fo = ForwardOutcome(bars_forward=10)
    result = fo.calculate(data[0].close, "SHORT", data)
    assert "pnl" in result
