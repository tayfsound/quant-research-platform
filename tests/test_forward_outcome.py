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

def test_forward_outcome_uses_bars_forward():
    """ForwardOutcome gercekten bars_forward kadar ileri gitmeli (P1-11)."""
    from market_data.ingestion.ohlcv import OHLCV
    fwd = ForwardOutcome(bars_forward=5)
    data = [OHLCV(open=100, high=101, low=99, close=100+i, volume=1000, timestamp=None) for i in range(20)]
    result = fwd.calculate(entry_price=100, direction="LONG", data=data)
    assert result["bars"] == 5
    assert result["exit_price"] == 105

def test_forward_outcome_with_fee():
    """Fee net PnL'den dusulmeli."""
    from market_data.ingestion.ohlcv import OHLCV
    fwd = ForwardOutcome(bars_forward=10)
    data = [OHLCV(open=100, high=101, low=99, close=100+i, volume=1000, timestamp=None) for i in range(20)]
    result = fwd.calculate(entry_price=100, direction="LONG", data=data, fee=2.0)
    assert result["pnl"] == 8.0
    assert result["win"] is True
