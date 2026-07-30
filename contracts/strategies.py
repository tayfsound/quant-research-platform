"""Strategy contracts (backward compatibility)."""
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class StrategyDefinition(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = "default"
    status: str = "active"
