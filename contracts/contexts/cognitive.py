"""CognitiveContext – zihinsel durum (inançlar, hipotezler)."""
from pydantic import BaseModel, Field


class CognitiveContext(BaseModel):
    active_beliefs: list[dict] = Field(default_factory=list)
    active_hypotheses: list[dict] = Field(default_factory=list)
    relevant_knowledge: list[dict] = Field(default_factory=list)
