"""Agent Weight Snapshot — immutable, event-sourced ağırlık kaydı."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentWeightSnapshot(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    weights: dict[str, float] = Field(default_factory=dict)

    evaluation_window: int = 0
    previous_snapshot_id: UUID | None = None
    snapshot_hash: str = ""
    reason: str = "performance_update"

    engine_version: str = "1.0.0"

    def compute_hash(self) -> str:
        payload = json.dumps(self.weights, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def finalize(self) -> "AgentWeightSnapshot":
        self.snapshot_hash = self.compute_hash()
        return self
