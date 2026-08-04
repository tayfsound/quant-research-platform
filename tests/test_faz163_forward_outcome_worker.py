"""Faz 163: ForwardOutcome Worker + Learning Trigger integration."""
from datetime import datetime, timezone
from services.pending_outcome_tracker import PendingOutcomeTracker
from services.forward_outcome import ForwardOutcome
from market_data.ingestion.mock_adapter import MockOHLCVAdapter

def test_forward_outcome_with_fee():
    fo = ForwardOutcome(bars_forward=5)
    adapter = MockOHLCVAdapter(seed=42)
    data = adapter.generate(10)
    
    result = fo.calculate(100.0, "LONG", data, fee=0.001)
    assert result["pending"] is False
    assert "gross_pnl" in result
    assert "fee" in result
    assert result["pnl"] == result["gross_pnl"] - result["fee"]
    assert result["fee"] > 0

def test_pending_tracker_finalize_triggers_learning():
    tracker = PendingOutcomeTracker()
    tracker.add("d-faz163", 100.0, "LONG", 5, datetime.now(timezone.utc))
    
    adapter = MockOHLCVAdapter(seed=42)
    provider = type("P", (), {"get_ohlcv": lambda self, s, t, limit: adapter.generate(limit)})()
    
    finalized = tracker.check_and_finalize(provider, "BTCUSDT", "1m")
    assert len(finalized) == 1
    assert "pnl" in finalized[0]["result"]
    assert tracker.count() == 0

def test_pending_tracker_persists_until_bars_arrive():
    tracker = PendingOutcomeTracker()
    tracker.add("d-pending", 100.0, "LONG", 100, datetime.now(timezone.utc))
    
    adapter = MockOHLCVAdapter(seed=42)
    provider = type("P", (), {"get_ohlcv": lambda self, s, t, limit: adapter.generate(5)})()
    
    finalized = tracker.check_and_finalize(provider, "BTCUSDT", "1m")
    assert len(finalized) == 0
    assert tracker.count() == 1
