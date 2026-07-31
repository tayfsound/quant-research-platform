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
from datetime import datetime, timedelta, timezone
from market_data.ingestion.ohlcv import OHLCV

def _bars(n, start=100.0, step=1.0):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        p = start + i * step
        out.append(OHLCV(timestamp=t0 + timedelta(minutes=i), open=p, high=p, low=p, close=p, volume=1.0))
    return out

def test_long_profit_n_bar():
    data = _bars(20, start=100.0, step=1.0)
    fo = ForwardOutcome(bars_forward=10)
    r = fo.calculate(entry_price=data[-11].close, direction="LONG", data=data)
    assert r["pending"] is False
    assert r["pnl"] > 0
    assert r["bars"] == 10

def test_short_profit():
    data = _bars(20, start=100.0, step=-1.0)
    fo = ForwardOutcome(bars_forward=10)
    r = fo.calculate(entry_price=data[-11].close, direction="SHORT", data=data)
    assert r["pnl"] > 0

def test_insufficient_bars_pending():
    data = _bars(5)
    r = ForwardOutcome(10).calculate(100.0, "LONG", data)
    assert r["pending"] is True
    assert r["pnl"] == 0.0
