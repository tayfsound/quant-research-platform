"""Trade sonuçlarını ve LLM açıklamalarını tutan veri modeli."""
from datetime import datetime
from uuid import uuid4

ALLOWED_ENSEMBLE_KEYS = {"direction", "confidence", "agent_votes", "model_versions"}

class ExperimentLog:
    def __init__(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        ensemble_data: dict,
        llm_explanation: dict,
        outcome: dict | None = None,
        id: str | None = None,
        timestamp: str | None = None,
    ):
        extra = set(ensemble_data) - ALLOWED_ENSEMBLE_KEYS
        if extra:
            raise ValueError(f"ensemble_data contains disallowed keys: {extra}")
        self.id = id or str(uuid4())[:8]
        self.timestamp = timestamp or datetime.now().isoformat()
        self.symbol = symbol
        self.direction = direction
        self.confidence = confidence
        self.ensemble_data = ensemble_data
        self.llm_explanation = llm_explanation
        self.outcome = outcome or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "ensemble_data": self.ensemble_data,
            "llm_explanation": self.llm_explanation,
            "outcome": self.outcome,
        }
