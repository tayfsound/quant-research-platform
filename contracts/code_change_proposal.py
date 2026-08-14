"""Code Change Proposal contract — Faz 270.

LLM'in (Respond sekmesi, NvidiaDecisionCritic.ask_with_tools()) önerdiği
kod değişikliklerinin insan onayı olmadan diske hiç yazılmadığı, sadece
biriktirildiği kuyruk."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class CodeChangeProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    title: str
    file_path: str
    description: str
    diff: str
    rationale: str
    status: str = "pending"  # pending | approved | rejected
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
