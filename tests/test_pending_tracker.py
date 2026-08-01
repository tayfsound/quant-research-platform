"""PendingOutcomeTracker unit tests."""
from datetime import datetime, timezone
from services.pending_outcome_tracker import PendingOutcomeTracker

def test_add_and_count():
    tracker = PendingOutcomeTracker()
    tracker.add("d1", 100.0, "LONG", 10, datetime.now(timezone.utc))
    assert tracker.count() == 1

def test_check_with_mock_data():
    from unittest.mock import MagicMock
    from market_data.ingestion.mock_adapter import MockOHLCVAdapter
    
    tracker = PendingOutcomeTracker()
    tracker.add("d1", 100.0, "LONG", 5, datetime.now(timezone.utc))
    
    mock_provider = MagicMock()
    adapter = MockOHLCVAdapter(seed=42)
    mock_provider.get_ohlcv.return_value = adapter.generate(20)
    
    finalized = tracker.check_and_finalize(mock_provider, "BTCUSDT", "1m")
    assert len(finalized) == 1
    assert "result" in finalized[0]
    assert tracker.count() == 0
