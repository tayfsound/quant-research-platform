"""LLM Sistem Denetimi çalışma kaydı — Faz 271."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class LLMAuditRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    response: str
    tool_calls: list[dict] = Field(default_factory=list)
    proposals_created: int = 0
