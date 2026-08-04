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

def test_check_and_finalize_with_real_provider():
    """Gerçek MockOHLCVAdapter ile pending → finalized dönüşümü."""
    from datetime import datetime, timezone
    from services.pending_outcome_tracker import PendingOutcomeTracker
    from market_data.ingestion.mock_adapter import MockOHLCVAdapter

    tracker = PendingOutcomeTracker()
    tracker.add("d1", 100.0, "LONG", 5, datetime.now(timezone.utc))

    # Gerçek adapter (seed=42 deterministik)
    provider = MockOHLCVAdapter(seed=42)
    data = provider.generate(20)

    # Mock provider yerine gerçek data
    class RealProvider:
        def get_ohlcv(self, symbol, timeframe, limit):
            return data

    finalized = tracker.check_and_finalize(RealProvider(), "BTCUSDT", "1m")
    assert len(finalized) == 1
    assert "result" in finalized[0]
    assert tracker.count() == 0
    assert "pnl" in finalized[0]["result"] or "pending" in finalized[0]["result"]
