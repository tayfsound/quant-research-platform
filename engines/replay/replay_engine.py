from services.replay.replay_verifier import ReplayVerifier


class DeterministicReplayEngine:

    def __init__(self, decision_engine):
        self.decision_engine = decision_engine
        self.verifier = ReplayVerifier()

    def replay(self, snapshot, event):

        replayed_decision = self.decision_engine.evaluate()

        verification = self.verifier.verify(
            snapshot,
            event,
        )

        return {
            "replayed_decision": replayed_decision,
            "verification": verification,
        }
