"""Cognitive Binding — UCEL Expression'ı bağlar."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from contracts.expression import Expression


class CognitiveBinding(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    source_type: str
    source_id: UUID | None = None
    expression: Expression
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)

    def evaluate(self, context: dict[str, float]) -> bool:
        return self.expression.evaluate(context).value.is_true()
