from collections.abc import Iterable


class ReplayEventStream:

    def __init__(self, events: Iterable[dict]):
        self.events = list(events)

    def __iter__(self):
        return iter(self.events)

    def count(self):
        return len(self.events)
