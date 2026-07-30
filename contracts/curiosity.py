"""Curiosity Engine + Experiment modelleri."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

class ExperimentPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ExperimentStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"

class CuriositySignal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    question: str
    source: str = "unknown"
    priority: ExperimentPriority = ExperimentPriority.MEDIUM
    information_gain: float = 0.5
    created_at: datetime = Field(default_factory=datetime.now)
    tested_count: int = 0

class ExperimentProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    curiosity_id: UUID = Field(default_factory=uuid4)
    hypothesis: str
    test_expression: str
    estimated_value: float = 0.0
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    expected_duration: int = 0
    required_samples: int = 100
    execution_mode: str = "experiment"
    created_at: datetime = Field(default_factory=datetime.now)

class ExperimentResult(BaseModel):
    """Deney sonucu — 'bu deney ne öğretti?' sorusuna cevap verir."""
    proposal_id: UUID
    samples: int = 0
    pnl: float = 0.0
    win_rate: float = 0.0
    confidence_change: float = 0.0
    conclusion: str = ""
    completed_at: datetime = Field(default_factory=datetime.now)
