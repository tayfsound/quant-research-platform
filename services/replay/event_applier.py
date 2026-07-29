class ReplayEventApplier:

    def __init__(self, state):
        self.state = state

    def apply(self, event: dict):

        event_type = event.get("event_type")

        if event_type == "market_update":
            self.state["market"] = event.get(
                "payload",
                {}
            )

        elif event_type == "belief_update":
            self.state["belief"] = event.get(
                "payload",
                {}
            )

        elif event_type == "risk_update":
            self.state["risk"] = event.get(
                "payload",
                {}
            )

        return self.state
