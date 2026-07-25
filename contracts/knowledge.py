"""Knowledge Memory — append-only deney kayıtları."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class KnowledgeCategory(StrEnum):
    EXPERIMENT = "experiment"
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    TRADE_RESULT = "trade_result"
    REFLECTION = "reflection"

class KnowledgeEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    category: KnowledgeCategory = KnowledgeCategory.OBSERVATION
    symbol: str | None = None
    timeframe: str | None = None
    conditions: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    source: str = ""
    immutable: bool = True
