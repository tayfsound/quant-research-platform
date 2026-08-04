from contracts.decision_event import DecisionEvent
from services.replay.replay_verifier import ReplayVerifier


class DeterministicReplayEngine:
    """Restores a ReplaySnapshot's state into decision_engine, re-runs the
    decision, and verifies the replayed outcome hashes identically to the
    original snapshot — the actual determinism proof, not a tautology."""

    def __init__(self, decision_engine):
        self.decision_engine = decision_engine
        self.verifier = ReplayVerifier()

    def replay(self, snapshot, event: DecisionEvent) -> dict:
        replayed_event = self.decision_engine.evaluate(snapshot)

        verification = self.verifier.verify(
            snapshot,
            replayed_event,
        )

        return {
            "replayed_decision": replayed_event,
            "verification": verification,
        }
