from services.replay.event_applier import ReplayEventApplier


class ReplaySession:

    def __init__(self, snapshot):
        self.state = {
            "market": snapshot.market_state,
            "risk": snapshot.risk_state,
            "belief": snapshot.belief_state,
        }

        self.applier = ReplayEventApplier(
            self.state
        )

    def run(self, events):

        for event in events:
            self.applier.apply(event)

        return self.state
