"""CouncilStage'dan once SourceReliabilityAgent calistiran wrapper."""

from agents.source_reliability_agent import SourceReliabilityAgent


class ReliabilityAnnotator:
    def __init__(self):
        self.agent = SourceReliabilityAgent()

    def annotate(self, opinions: list[dict], symbol: str | None = None) -> list[dict]:
        return self.agent.annotate(opinions, symbol=symbol)
