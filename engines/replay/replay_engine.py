from contracts.replay.replay_result import ReplayResult


class ReplayEngine:

    def __init__(self, decision_engine):
        self.decision_engine = decision_engine

    def replay(self, snapshot, events):

        for event in events:
            self._apply_event(event)

        decision = self.decision_engine.evaluate()

        return decision

    def verify(self, original, replayed):

        differences = {}

        if original != replayed:
            differences["decision"] = {
                "original": original,
                "replayed": replayed
            }

        return ReplayResult(
            success=True,
            verified=len(differences) == 0,
            original_decision=original,
            replayed_decision=replayed,
            differences=differences
        )

    def _apply_event(self, event):
        pass
