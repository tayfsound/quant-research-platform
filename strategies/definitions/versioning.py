"""Strateji versiyonlama ve soy takibi."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel


class StrategyVersion(BaseModel):
    id: UUID = uuid4()
    strategy_name: str
    version: int = 1
    parent_version: int | None = None
    parameters: dict = {}
    created_at: datetime = datetime.now()
    changelog: str = ""
