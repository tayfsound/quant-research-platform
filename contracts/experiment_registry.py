"""Experiment Registry contract — Faz 159."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class ExperimentRegistry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    git_sha: str = ""
    risk_limits_version: int = 0
    feature_schema_id: str = ""
    prompt_hash: str = ""
    model_id: str = ""
    decision_ids: list[str] = Field(default_factory=list)
