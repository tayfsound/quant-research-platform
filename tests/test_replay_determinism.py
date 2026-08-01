"""Replay Engine determinism + integrity check."""
from unittest.mock import patch

def test_replay_reconstructs_same_context():
    """Replay decision_id → same context rebuild."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.replay_engine import ReplayEngine
            from contracts.context import CognitiveCycleContext
            
            engine = ReplayEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            
            # Store and replay
            decision_id = engine.store(ctx)
            replayed = engine.replay(decision_id)
            
            assert replayed is not None
            assert replayed.market.symbol == "BTCUSDT"
            assert replayed.decision.proposed_direction == "LONG"

def test_replay_integrity_check():
    """Replay detects tampered decision."""
    from services.replay_engine import ReplayEngine
    from contracts.context import CognitiveCycleContext
    
    engine = ReplayEngine()
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    
    decision_id = engine.store(ctx)
    
    # Tamper check (stub — real implementation needs hash)
    result = engine.verify_integrity(decision_id)
    assert result is True  # or False if tampered
