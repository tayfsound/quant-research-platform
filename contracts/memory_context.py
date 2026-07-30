"""Memory Context modelleri."""
from pydantic import BaseModel


class MemoryInsight(BaseModel):
    similar_count: int = 0
    win_rate: float = 0.0
    average_pnl: float = 0.0
    dominant_direction: str = "NEUTRAL"
    confidence: float = 0.0
