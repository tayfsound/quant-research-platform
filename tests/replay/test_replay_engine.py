from datetime import UTC, datetime

from contracts.decision_event import DecisionEvent
from engines.replay.replay_engine import DeterministicReplayEngine
from services.replay.snapshot_builder import build_snapshot


class FakeDecisionEngine:

    def evaluate(self):
        return {
            "action": "BUY"
        }


def test_replay_engine():

    event = DecisionEvent(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        final_action="BUY",
        final_size=1.0,
        confidence=0.8,
    )

    snapshot = build_snapshot(event)

    engine = DeterministicReplayEngine(
        FakeDecisionEngine()
    )

    result = engine.replay(
        snapshot,
        event,
    )

    assert result["verification"]["verified"] is True
