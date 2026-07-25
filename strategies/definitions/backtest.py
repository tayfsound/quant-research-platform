"""Ensemble backtest altyapısı."""

from strategies.definitions.ensemble import AgentVote, WeightedVoting


class EnsembleBacktester:
    def __init__(self, voting: WeightedVoting):
        self.voting = voting
        self._results: list[dict] = []

    def run(self, historical_votes: list[list[AgentVote]]) -> list[dict]:
        for votes in historical_votes:
            decision = self.voting.decide(votes)
            self._results.append({"direction": decision.direction, "confidence": decision.confidence})
        return self._results
