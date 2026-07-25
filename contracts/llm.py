"""LLM portları ve şemaları."""
from abc import abstractmethod
from typing import Protocol

from pydantic import BaseModel, Field


class LLMExplanation(BaseModel):
    explanation: str = ""
    risks: list[str] = Field(default_factory=list)
    confidence_comment: str = ""
    risk_adjustment_factor: float = Field(default=1.0, ge=0.5, le=1.0)

    @classmethod
    def neutral(cls) -> "LLMExplanation":
        return cls(
            explanation="LLM unavailable - proceeding with neutral adjustment",
            risks=["LLM timeout - no risk adjustment applied"],
            confidence_comment="Neutral fallback due to timeout",
            risk_adjustment_factor=1.0,
        )

class LLMExplainerPort(Protocol):
    @abstractmethod
    async def explain(self, ensemble_output: dict, prompt: str = "", timeout_ms: int = 500) -> LLMExplanation:
        """Timeout'ta LLMExplanation.neutral() döner, asla exception fırlatmaz."""
        ...

    @abstractmethod
    async def analyze_logs(self, logs: list[dict], current_prompt: str) -> dict: ...
