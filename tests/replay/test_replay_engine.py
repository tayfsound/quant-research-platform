from datetime import UTC, datetime

from contracts.decision_event import DecisionEvent
from engines.replay.replay_engine import DeterministicReplayEngine
from services.replay.snapshot_builder import build_snapshot


class FakeDecisionEngine:
    """Simulates a decision engine that reruns a decision from restored state."""

    def __init__(self, final_action="BUY", final_size=1.0):
        self.final_action = final_action
        self.final_size = final_size

    def evaluate(self, snapshot):
        return DecisionEvent(
            symbol=snapshot.market_state.get("symbol", "BTCUSDT"),
            final_action=self.final_action,
            final_size=self.final_size,
            confidence=0.8,
            market_snapshot=snapshot.market_state,
            risk_evaluation=snapshot.risk_state,
            belief_state=snapshot.belief_state,
        )


def test_replay_engine_verifies_when_replay_matches():
    event = DecisionEvent(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        final_action="BUY",
        final_size=1.0,
        confidence=0.8,
        market_snapshot={"price": 60000},
        risk_evaluation={"verdict": "approved"},
        belief_state={"trend": "bullish"},
    )
    snapshot = build_snapshot(event)

    engine = DeterministicReplayEngine(FakeDecisionEngine(final_action="BUY", final_size=1.0))
    result = engine.replay(snapshot, event)

    assert result["verification"]["verified"] is True


def test_replay_engine_flags_divergence_when_replay_differs():
    """If the re-run produces a different decision, verification must catch it — not just echo the original."""
    event = DecisionEvent(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        final_action="BUY",
        final_size=1.0,
        confidence=0.8,
        market_snapshot={"price": 60000},
        risk_evaluation={"verdict": "approved"},
        belief_state={"trend": "bullish"},
    )
    snapshot = build_snapshot(event)

    engine = DeterministicReplayEngine(FakeDecisionEngine(final_action="SELL", final_size=2.0))
    result = engine.replay(snapshot, event)

    assert result["verification"]["verified"] is False
