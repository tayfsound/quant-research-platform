"""Training Feature Extractor — Phase 173."""

from dataclasses import dataclass


@dataclass
class TrainingFeatures:
    confidence: float
    size: float
    agent_count: int
    pnl: float
    label: int


class TrainingFeatureExtractor:

    def extract(self, row: dict) -> TrainingFeatures:
        agents = row.get("agent_contributions") or []

        return TrainingFeatures(
            confidence=row.get("confidence") or 0.0,
            size=row.get("size") or 0.0,
            agent_count=len(agents),
            pnl=row.get("pnl") or 0.0,
            label=1 if (row.get("pnl") or 0) > 0 else 0,
        )
