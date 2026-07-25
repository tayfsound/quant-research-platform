"""Experiment Registry — soy ağacı ve tam reproducibility."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExperimentStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"

class ExperimentVerdict(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    SUPERSEDED = "superseded"

class ExperimentMetrics(BaseModel):
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown: float | None = None
    sample_size: int = 0
    confidence_interval: tuple[float, float] | None = None
    p_value: float | None = None

class Experiment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    hypothesis_id: UUID | None = None
    parent_experiment: UUID | None = None
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    prompt_version: str = ""
    prompt_hash: str = ""
    model_version: str = ""
    risk_version: str = ""
    feature_version: str = ""
    strategy_version: str = ""
    git_commit: str = ""
    python_version: str = ""
    package_hash: str = ""
    config_hash: str = ""
    start_date: datetime | None = None
    end_date: datetime | None = None
    metrics: ExperimentMetrics = Field(default_factory=ExperimentMetrics)
    verdict: ExperimentVerdict | None = None
    created_at: datetime = Field(default_factory=datetime.now)
