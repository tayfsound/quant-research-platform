"""CouncilStage'dan once SourceReliabilityAgent calistiran wrapper."""
from typing import List, Dict
from agents.source_reliability_agent import SourceReliabilityAgent

class ReliabilityAnnotator:
    def __init__(self):
        self.agent = SourceReliabilityAgent()

    def annotate(self, opinions: List[Dict], symbol: str | None = None) -> List[Dict]:
        return self.agent.annotate(opinions, symbol=symbol)
