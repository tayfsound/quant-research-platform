from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReplaySnapshot:
    snapshot_id: str
    created_at: datetime

    decision_event_id: str = ""

    market_state: dict[str, Any] = field(default_factory=dict)
    risk_state: dict[str, Any] = field(default_factory=dict)

    beliefs: dict[str, Any] = field(default_factory=dict)
    belief_state: dict[str, Any] = field(default_factory=dict)

    weight_snapshot_id: str | None = None

    decision_hash: str = ""
