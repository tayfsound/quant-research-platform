"""Self Evaluation modelleri — ajanın kendini değerlendirmesi."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class PredictionError(BaseModel):
    """Tahmin hatası kaydı."""
    episode_id: UUID
    symbol: str
    predicted_direction: str
    actual_outcome: str          # "win", "loss", "neutral"
    error_magnitude: float = 0.0 # PnL bazlı hata büyüklüğü
    conditions: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

class OutcomeAnalysis(BaseModel):
    """Sonuç analizi."""
    total_evaluated: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    condition_breakdown: dict[str, dict] = Field(default_factory=dict)
    top_error_conditions: list[str] = Field(default_factory=list)

class BeliefAdjustment(BaseModel):
    """Belief güncelleme önerisi."""
    belief_expression: str
    old_confidence: float
    new_confidence: float
    reason: str
    adjustment_type: str  # "strengthen", "weaken", "invalidate"

class Lesson(BaseModel):
    """Çıkarılan ders."""
    id: UUID = Field(default_factory=uuid4)
    episode_id: UUID | None = None
    lesson_text: str
    category: str = "general"    # "condition_specific", "regime", "model_error"
    severity: str = "info"       # "info", "warning", "critical"
    created_at: datetime = Field(default_factory=datetime.now)
