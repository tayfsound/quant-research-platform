"""Observation — ham veriden ilk işlenmiş bilgi katmanı."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ObservationType(StrEnum):
    EXPERIMENT = "experiment"
    PRICE_ACTION = "price_action"
    INDICATOR = "indicator"
    PATTERN = "pattern"
    ANOMALY = "anomaly"
    CORRELATION = "correlation"
    REGIME_CHANGE = "regime_change"

class Observation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    type: ObservationType
    symbol: str
    timeframe: str
    description: str                    # İnsan için
    expression: str = ""                # Makine için: "RSI<30 AND VOLUME>AVG"
    data: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = ""                    # Hangi pipeline'dan geldiği
